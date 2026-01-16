# claude.py
"""
Module pour lancer Claude Code de manière programmatique avec streaming des logs.
Architecture async native pour éviter les timeouts.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp
import websockets


# =============================================================================
# Configuration
# =============================================================================

# URL du serveur WebSocket CRE_INTERFACE (configurable via env)
WS_BASE_URL = os.environ.get("CRE_WS_URL", "ws://192.36.128.62:8080")
# URL HTTP pour l'upload des artifacts
HTTP_BASE_URL = os.environ.get("CRE_HTTP_URL", "http://192.36.128.62:8080")


# =============================================================================
# Utilitaires
# =============================================================================

def log_to_stderr(text: str) -> None:
    """Log vers stderr pour voir en temps réel dans le terminal."""
    sys.stderr.write(text)
    sys.stderr.flush()


def strip_ansi(text: str) -> str:
    """Supprime les séquences ANSI de contrôle (couleurs, curseur, etc.)."""
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    text = ansi_escape.sub('', text)
    text = re.sub(r'\x1B\].*?(?:\x07|\x1B\\)', '', text)
    text = re.sub(r'\x1B[()][AB012]', '', text)
    text = re.sub(r'\x1B[@-_]', '', text)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', text)
    return text


# switch_branch() supprimé - remplacé par WorktreeManager dans .claude/worktree.py


# =============================================================================
# WebSocket Notifier
# =============================================================================

@dataclass
class StepInfo:
    """Informations sur une étape en cours."""
    name: str
    status: str = "running"


class WebSocketNotifier:
    """
    Gère la communication WebSocket pour notifier l'avancement.
    Encapsule toute la logique de messaging avec support de reconnexion.
    """

    STEPS = [
        "setup",           # Initialisation
        "phase1_parallel_analyzer_security_reviewer",          # ANALYZER + SECURITY + REVIEWER (parallèle)
        "phase2_risk",     # RISK
        "phase2_parallel_synthesis_sonar", # SYNTHESIS + SONAR (parallèle)
        "phase3_meta_synthesis",          # META-SYNTHESIS
        "phase4_web_synthesizer",          # WEB-SYNTHESIZER
        "report"           # Envoi du rapport final
    ]

    # Mapping agent -> phase
    AGENT_TO_PHASE = {
        "analyzer": "phase1_parallel_analyzer_security_reviewer",
        "security": "phase1_parallel_analyzer_security_reviewer",
        "reviewer": "phase1_parallel_analyzer_security_reviewer",
        "risk": "phase2_risk",
        "synthesis": "phase2_parallel_synthesis_sonar",
        "sonar": "phase2_parallel_synthesis_sonar",
        "meta-synthesis": "phase3_meta_synthesis",
        "web-synthesizer": "phase4_web_synthesizer",
    }

    def __init__(self, websocket, ws_url: str = None, job_id: str = None):
        self.ws = websocket
        self.ws_url = ws_url      # URL pour reconnexion
        self.job_id = job_id      # Job ID pour reconnexion
        self.current_step: Optional[str] = None
        self.action_status: str = "success"
        self.action_completed: bool = False
        self.action_started_sent: bool = False  # Track si action_started a été envoyé
        self.agents_in_phase: dict[str, set] = {}  # phase -> set d'agents lancés
        self.report_path: Optional[str] = None     # Chemin du rapport final
        # Référence à la tâche de monitoring WebSocket (pour l'annuler avant send_artifact)
        self.monitor_task: Optional[asyncio.Task] = None
        # Queue de messages en cas de déconnexion
        self._message_queue: list[dict] = []
        self._connected: bool = True
        self._reconnect_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Vérifie si le WebSocket est connecté."""
        if self.ws is None:
            return False
        try:
            from websockets.protocol import State
            return self.ws.state == State.OPEN
        except Exception:
            return False

    async def reconnect(self, max_retries: int = 5, base_delay: float = 1.0) -> bool:
        """
        Tente de se reconnecter au WebSocket avec backoff exponentiel.

        Args:
            max_retries: Nombre maximum de tentatives
            base_delay: Délai initial entre les tentatives (secondes)

        Returns:
            True si reconnecté, False sinon
        """
        async with self._reconnect_lock:
            if self.connected:
                return True

            if not self.ws_url or not self.job_id:
                log_to_stderr("[WS] Cannot reconnect: missing ws_url or job_id\n")
                return False

            full_url = f"{self.ws_url}/{self.job_id}"

            for attempt in range(1, max_retries + 1):
                delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff
                log_to_stderr(f"\n🔄 [WS] Reconnection attempt {attempt}/{max_retries}...\n")

                try:
                    # Fermer l'ancienne connexion proprement
                    if self.ws:
                        try:
                            await self.ws.close()
                        except Exception:
                            pass

                    # Nouvelle connexion
                    async with asyncio.timeout(10):
                        self.ws = await websockets.connect(full_url)

                    # Attendre le message "connected"
                    async with asyncio.timeout(5):
                        connected_msg = await self.ws.recv()
                        connected_data = json.loads(connected_msg)
                        if connected_data.get("type") == "connected":
                            log_to_stderr(f"✅ [WS] Reconnected successfully!\n")
                            self._connected = True

                            # Restaurer l'état côté serveur
                            await self._restore_state()

                            # Envoyer les messages en queue
                            await self._flush_queue()

                            return True
                        else:
                            log_to_stderr(f"⚠️ [WS] Unexpected message: {connected_data.get('type')}\n")

                except asyncio.TimeoutError:
                    log_to_stderr(f"⚠️ [WS] Reconnection timeout (attempt {attempt})\n")
                except websockets.exceptions.WebSocketException as e:
                    log_to_stderr(f"⚠️ [WS] Reconnection failed: {e}\n")
                except Exception as e:
                    log_to_stderr(f"⚠️ [WS] Reconnection error: {type(e).__name__}: {e}\n")

                if attempt < max_retries:
                    log_to_stderr(f"⏳ [WS] Waiting {delay:.1f}s before next attempt...\n")
                    await asyncio.sleep(delay)

            log_to_stderr(f"❌ [WS] Failed to reconnect after {max_retries} attempts\n")
            return False

    async def _restore_state(self) -> None:
        """Restaure l'état de l'action après reconnexion."""
        # Re-envoyer action_started si déjà envoyé
        if self.action_started_sent and not self.action_completed:
            await self._send_direct({
                "type": "action_started",
                "steps": self.STEPS
            })
            log_to_stderr(f"📋 [WS] Restored action_started\n")

            # Re-envoyer l'étape en cours si présente
            if self.current_step:
                await self._send_direct({
                    "type": "step_started",
                    "step": self.current_step
                })
                log_to_stderr(f"📋 [WS] Restored current step: {self.current_step}\n")

    async def _flush_queue(self) -> None:
        """Envoie tous les messages en queue."""
        if not self._message_queue:
            return

        log_to_stderr(f"📤 [WS] Flushing {len(self._message_queue)} queued messages...\n")
        queue_copy = self._message_queue.copy()
        self._message_queue.clear()

        for msg in queue_copy:
            try:
                await self._send_direct(msg)
            except Exception as e:
                log_to_stderr(f"⚠️ [WS] Failed to send queued message: {e}\n")
                # Re-queue le message si échec
                self._message_queue.append(msg)
                break

    async def _send_direct(self, message: dict) -> None:
        """Envoie directement sans queue (utilisé pour restore/flush)."""
        if self.ws:
            await self.ws.send(json.dumps(message))

    async def send(self, message: dict) -> None:
        """Envoie un message JSON au WebSocket, avec queue si déconnecté."""
        if not self.connected:
            # Queue le message pour envoi après reconnexion
            self._message_queue.append(message)
            # Limiter la taille de la queue (garder les 1000 derniers messages)
            if len(self._message_queue) > 1000:
                self._message_queue = self._message_queue[-1000:]
            return

        try:
            await self.ws.send(json.dumps(message))
        except websockets.exceptions.ConnectionClosed:
            log_to_stderr("[WS] Connection closed, queuing message\n")
            self._connected = False
            self._message_queue.append(message)

    async def action_started(self) -> None:
        """Notifie le début de l'action avec les étapes."""
        self.action_started_sent = True
        await self.send({
            "type": "action_started",
            "steps": self.STEPS
        })

    async def step_started(self, step: str) -> None:
        """Notifie le début d'une étape."""
        self.current_step = step
        await self.send({
            "type": "step_started",
            "step": step
        })

    async def step_log(self, line: str, stream: str = "stdout") -> None:
        """Envoie un log pour l'étape en cours."""
        if not self.current_step:
            return
        await self.send({
            "type": "step_log",
            "step": self.current_step,
            "line": line,
            "stream": stream
        })

    async def step_complete(self, status: str, output: str = "") -> None:
        """Marque l'étape en cours comme terminée."""
        if not self.current_step:
            return
        if status == "failure":
            self.action_status = "failure"
        await self.send({
            "type": "step_complete",
            "step": self.current_step,
            "status": status,
            "output": output
        })

    async def action_complete(self) -> None:
        """Marque l'action comme terminée."""
        if self.action_completed:
            return
        self.action_completed = True
        await self.send({
            "type": "action_complete",
            "status": self.action_status
        })

    async def transition_to(self, new_step: str, prev_output: str = "") -> None:
        """Transition propre d'une étape à une autre."""
        if self.current_step and self.current_step != new_step:
            await self.step_complete("success", prev_output)
        await self.step_started(new_step)

    async def fail_with_error(self, error_msg: str) -> None:
        """
        Termine l'action avec une erreur de manière conforme au protocole.
        Envoie step_complete(failure) puis action_complete(failure).
        """
        # S'assurer qu'on a une step en cours pour le step_complete
        if not self.current_step:
            await self.step_started("setup")

        await self.step_log(f"Error: {error_msg}", "stderr")
        await self.step_complete("failure", f"## Error\n\n{error_msg}")
        await self.action_complete()

    async def on_agent_started(self, agent_type: str) -> None:
        """Gère le lancement d'un agent et la transition de phase."""
        phase = self.AGENT_TO_PHASE.get(agent_type)
        if not phase:
            return

        # Tracker l'agent dans sa phase
        if phase not in self.agents_in_phase:
            self.agents_in_phase[phase] = set()
        self.agents_in_phase[phase].add(agent_type)

        # Transition vers la nouvelle phase si nécessaire
        if self.current_step != phase:
            await self.transition_to(phase, f"Completed {self.current_step}")

    async def send_artifact(self, file_path: str, artifact_type: str = "report") -> bool:
        """
        Envoie un artifact selon le protocole complet:
        1. Envoie message 'artifact' (notification)
        2. Attend 'artifact_ready' du serveur
        3. Upload le fichier via HTTP POST multipart

        Args:
            file_path: Chemin du fichier artifact
            artifact_type: Type d'artifact (binary, report, log, coverage, file)

        Returns:
            True si l'artifact a été uploadé avec succès, False sinon
        """
        self.report_path = file_path
        path = Path(file_path)

        if not path.exists():
            log_to_stderr(f"\n❌ Artifact file not found: {file_path}\n")
            return False

        try:
            # 1. Envoyer la notification artifact (SANS path/size selon protocole)
            await self.send({
                "type": "artifact",
                "step": self.current_step or "report",
                "artifact": {
                    "name": path.name,
                    "type": artifact_type
                }
            })
            log_to_stderr(f"\n📤 Artifact notification sent: {path.name}\n")

            # 2. Attendre artifact_ready du serveur (timeout 30s)
            # D'abord, annuler la tâche de monitoring pour éviter les conflits recv()
            # (l'analyse est terminée à ce stade, on n'a plus besoin du monitoring)
            if self.monitor_task and not self.monitor_task.done():
                self.monitor_task.cancel()
                try:
                    await self.monitor_task
                except asyncio.CancelledError:
                    pass
                log_to_stderr("📡 Monitor task cancelled for artifact upload\n")

            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=30)
                data = json.loads(response)

                if data.get("type") != "artifact_ready":
                    log_to_stderr(f"\n⚠️ Expected 'artifact_ready', got: {data.get('type')}\n")
                    return False

                artifact_id = data.get("artifactId")
                upload_url = data.get("uploadUrl")

                if not artifact_id or not upload_url:
                    log_to_stderr(f"\n❌ Missing artifactId or uploadUrl in response\n")
                    return False

                log_to_stderr(f"\n✅ Artifact ready: {artifact_id}, uploading to {upload_url}\n")

            except asyncio.TimeoutError:
                log_to_stderr(f"\n❌ Timeout waiting for artifact_ready\n")
                return False

            # 3. Upload HTTP du fichier (multipart/form-data)
            full_url = f"{HTTP_BASE_URL}{upload_url}"

            async with aiohttp.ClientSession() as session:
                with open(path, 'rb') as f:
                    form = aiohttp.FormData()
                    form.add_field(
                        'file',
                        f,
                        filename=path.name,
                        content_type='application/octet-stream'
                    )

                    async with session.post(full_url, data=form) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            log_to_stderr(f"\n✅ Artifact uploaded: {result.get('downloadUrl', '')}\n")
                            return True
                        elif resp.status == 409:
                            log_to_stderr(f"\n⚠️ Artifact already uploaded\n")
                            return True  # Considéré comme succès
                        elif resp.status == 413:
                            log_to_stderr(f"\n❌ Artifact too large (max 500MB)\n")
                            return False
                        else:
                            error_text = await resp.text()
                            log_to_stderr(f"\n❌ Upload failed ({resp.status}): {error_text}\n")
                            return False

        except websockets.exceptions.ConnectionClosed:
            log_to_stderr(f"\n❌ WebSocket closed during artifact upload\n")
            return False
        except aiohttp.ClientError as e:
            log_to_stderr(f"\n❌ HTTP error during upload: {e}\n")
            return False
        except Exception as e:
            log_to_stderr(f"\n❌ Failed to send artifact: {e}\n")
            return False


# =============================================================================
# Handlers pour les outils Claude
# =============================================================================

TOOL_FORMATTERS = {
    "Bash": lambda inp: f"$ {inp.get('command', '')[:200]}",
    "Read": lambda inp: f"📄 {inp.get('file_path', '')}",
    "Edit": lambda inp: f"✏️  {inp.get('file_path', '')}",
    "Write": lambda inp: f"📝 {inp.get('file_path', '')}",
    "Grep": lambda inp: f"🔍 Pattern: {inp.get('pattern', '')}",
    "Glob": lambda inp: f"📂 Pattern: {inp.get('pattern', '')}",
    "Task": lambda inp: f"🚀 {inp.get('subagent_type', 'agent')}: {inp.get('description', '')}",
}


def format_tool_log(tool_name: str, tool_input: dict) -> str:
    """Formate le log d'un outil de manière concise."""
    formatter = TOOL_FORMATTERS.get(tool_name)
    if formatter:
        return f"🔧 {tool_name}: {formatter(tool_input)}"
    return f"🔧 {tool_name}: {json.dumps(tool_input, ensure_ascii=False)[:200]}"


# =============================================================================
# Processeur d'événements Claude
# =============================================================================

class ClaudeEventProcessor:
    """
    Traite les événements JSON streamés par Claude.
    Sépare la logique de parsing de la logique de notification.
    """

    def __init__(self, notifier: WebSocketNotifier, verbosity: int = 1, working_dir: Path = None):
        self.notifier = notifier
        self.verbosity = verbosity
        self.working_dir = working_dir  # Répertoire de travail (worktree) pour résoudre les chemins relatifs
        self.result_text = ""
        self.total_cost = 0.0
        self.messages = []
        self.pending_report_path: Optional[str] = None  # Chemin du rapport détecté

    async def process_event(self, event: dict) -> None:
        """Traite un événement JSON de Claude."""
        event_type = event.get("type", "")

        if self.verbosity >= 2:
            log_to_stderr(f"\n[DEBUG] {event_type}: {json.dumps(event, ensure_ascii=False)[:500]}\n")

        handler = getattr(self, f"_handle_{event_type}", None)
        if handler:
            await handler(event)

        self.messages.append(event)

    async def _handle_assistant(self, event: dict) -> None:
        """Traite les messages de l'assistant."""
        content = event.get("message", {}).get("content", [])

        for block in content:
            block_type = block.get("type")

            if block_type == "text":
                text = block.get("text", "")
                self.result_text += text
                log_to_stderr(text)
                await self.notifier.step_log(text.strip())

            elif block_type == "tool_use":
                await self._handle_tool_use(block)

            elif block_type == "thinking":
                thinking = block.get("thinking", "")
                preview = thinking[:500] + "..." if len(thinking) > 500 else thinking
                log_to_stderr(f"\n💭 [Thinking]: {preview}\n")
                await self.notifier.step_log(f"[Thinking] {thinking[:200]}")

    async def _handle_tool_use(self, block: dict) -> None:
        """Traite l'utilisation d'un outil."""
        tool_name = block.get("name", "unknown")
        tool_input = block.get("input", {})

        # Détecter les agents Task
        if tool_name == "Task":
            agent_type = tool_input.get("subagent_type", "")
            if agent_type:
                await self.notifier.on_agent_started(agent_type)
                tool_log = f"🚀 Agent: {agent_type} - {tool_input.get('description', '')}"
                log_to_stderr(f"\n{tool_log}\n")
                await self.notifier.step_log(tool_log)
                return

        # Détecter la création du rapport web (Bash ou Write)
        if tool_name in ("Bash", "Write"):
            content = tool_input.get("command", "") or tool_input.get("file_path", "")
            # Pattern: reports/web-report-YYYY-MM-DD-commit.json
            match = re.search(r'reports/web-report-[\w-]+\.json', content)
            if match:
                relative_path = match.group(0)
                # Construire le chemin absolu depuis le working_dir (worktree)
                if self.working_dir:
                    self.pending_report_path = str(self.working_dir / relative_path)
                else:
                    self.pending_report_path = relative_path
                log_to_stderr(f"\n📋 Report will be created: {self.pending_report_path}\n")

        tool_log = format_tool_log(tool_name, tool_input)
        log_to_stderr(f"\n{tool_log}\n")
        await self.notifier.step_log(tool_log)

    async def _handle_content_block_start(self, event: dict) -> None:
        """Traite le début d'un bloc de contenu."""
        block = event.get("content_block", {})
        block_type = block.get("type", "")

        if block_type == "tool_use":
            log_to_stderr(f"\n⏳ Starting tool: {block.get('name', '')}...\n")
        elif block_type == "thinking":
            log_to_stderr("\n💭 [Claude réfléchit...]\n")

    async def _handle_content_block_delta(self, event: dict) -> None:
        """Traite le streaming de contenu."""
        delta = event.get("delta", {})
        delta_type = delta.get("type", "")

        if delta_type == "text_delta":
            text = delta.get("text", "")
            self.result_text += text
            log_to_stderr(text)
        elif delta_type == "thinking_delta":
            log_to_stderr(f"💭 {delta.get('thinking', '')}")

    async def _handle_user(self, event: dict) -> None:
        """Traite les messages utilisateur (résultats d'outils)."""
        content = event.get("message", {}).get("content", [])

        for block in content:
            if block.get("type") != "tool_result":
                continue

            tool_content = block.get("content", "")
            is_error = block.get("is_error", False)

            # Tronquer si trop long
            if isinstance(tool_content, str):
                display = tool_content[:300] + "..." if len(tool_content) > 300 else tool_content
            else:
                display = str(tool_content)[:300]

            if is_error:
                log_to_stderr(f"\n❌ Tool Error: {display}\n")
                await self.notifier.step_log(f"❌ Error: {display}", "stderr")
            else:
                log_to_stderr(f"\n✅ Tool Result: {display}\n")
                await self.notifier.step_log(f"✅ Result: {display[:200]}")

    async def _handle_system(self, event: dict) -> None:
        """Traite les messages système."""
        subtype = event.get("subtype", "")
        log_to_stderr(f"\n🔔 [System - {subtype}]\n")
        await self.notifier.step_log(f"[System] {subtype}")

    async def _handle_result(self, event: dict) -> None:
        """Traite le résultat final."""
        self.total_cost = event.get("cost_usd", 0.0)
        log_to_stderr(f"\n\n💰 Cost: ${self.total_cost:.4f}\n")

        # Transition vers la phase report
        await self.notifier.transition_to("report", "Analysis phases completed")
        await self.notifier.step_log(f"💰 Cost: ${self.total_cost:.4f}")

        # Construire le résumé spécifique à la phase report
        report_summary_lines = [f"💰 Cost: ${self.total_cost:.4f}"]
        step_status = "success"

        # Envoyer le rapport JSON si détecté
        if self.pending_report_path:
            await self.notifier.step_log(f"📤 Sending artifact: {self.pending_report_path}")
            artifact_sent = await self.notifier.send_artifact(self.pending_report_path, "analysis-report")
            if artifact_sent:
                report_summary_lines.append(f"📤 Artifact sent: {self.pending_report_path}")
            else:
                report_summary_lines.append(f"❌ Failed to send artifact: {self.pending_report_path}")
                step_status = "failure"
        else:
            log_to_stderr("\n⚠️ No report path detected\n")
            await self.notifier.step_log("⚠️ No report path detected", "stderr")
            report_summary_lines.append("⚠️ No report path detected")

        # Finaliser avec le résumé spécifique à la phase report
        report_summary = "\n".join(report_summary_lines)
        await self.notifier.step_complete(step_status, f"## Report\n\n{report_summary}")
        await self.notifier.action_complete()

    async def _handle_error(self, event: dict) -> None:
        """Traite les erreurs."""
        error_msg = event.get("error", {}).get("message", "Unknown error")
        log_to_stderr(f"\n❌ Erreur: {error_msg}\n")
        await self.notifier.step_log(f"Error: {error_msg}", "stderr")
        await self.notifier.step_complete("failure", f"## Error\n\n{error_msg}")
        await self.notifier.action_complete()


# =============================================================================
# Fonction principale de streaming
# =============================================================================

async def read_stream(stream, processor: ClaudeEventProcessor) -> None:
    """
    Lit un stream de manière asynchrone et traite les événements JSON.

    Utilise une lecture par chunks pour éviter l'erreur:
    "Separator is not found, and chunk exceed the limit"
    qui survient quand Claude génère des lignes JSON très longues
    (ex: tool_result avec beaucoup de données, rapports markdown).
    """
    buffer = b""
    CHUNK_SIZE = 64 * 1024  # 64KB par lecture
    MAX_LINE_SIZE = 128 * 1024 * 1024  # 128MB max par ligne (sécurité mémoire)

    while True:
        # Lire un chunk de données brutes (sans limite de taille de ligne)
        chunk = await stream.read(CHUNK_SIZE)
        if not chunk:
            # Fin du stream - traiter le reste du buffer s'il y en a
            if buffer:
                await _process_json_line(buffer.decode('utf-8', errors='replace').strip(), processor)
            break

        buffer += chunk

        # Protection mémoire: si le buffer devient trop grand sans newline, on a un problème
        if len(buffer) > MAX_LINE_SIZE and b'\n' not in buffer:
            log_to_stderr(f"\n⚠️ Warning: JSON line exceeds {MAX_LINE_SIZE // (1024*1024)}MB limit, truncating\n")
            # Traiter ce qu'on a et recommencer
            await _process_json_line(buffer[:MAX_LINE_SIZE].decode('utf-8', errors='replace').strip(), processor)
            buffer = buffer[MAX_LINE_SIZE:]

        # Traiter toutes les lignes complètes dans le buffer
        while b'\n' in buffer:
            line_bytes, buffer = buffer.split(b'\n', 1)
            line = line_bytes.decode('utf-8', errors='replace').strip()
            if line:
                await _process_json_line(line, processor)


async def _process_json_line(line: str, processor: ClaudeEventProcessor) -> None:
    """Traite une ligne JSON individuelle."""
    if not line:
        return
    try:
        event = json.loads(line)
        await processor.process_event(event)
    except json.JSONDecodeError:
        # Ligne non-JSON (ex: output brut de Claude)
        log_to_stderr(f"{line}\n")


async def read_stderr(stream) -> str:
    """
    Lit stderr de manière asynchrone avec lecture par chunks.
    Même approche que read_stream() pour éviter les problèmes de buffer.
    """
    output = []
    buffer = b""
    CHUNK_SIZE = 64 * 1024  # 64KB par lecture

    while True:
        chunk = await stream.read(CHUNK_SIZE)
        if not chunk:
            # Traiter le reste du buffer à la fin
            if buffer:
                decoded = buffer.decode('utf-8', errors='replace')
                output.append(decoded)
                log_to_stderr(f"[stderr] {decoded}")
            break

        buffer += chunk

        # Traiter toutes les lignes complètes
        while b'\n' in buffer:
            line_bytes, buffer = buffer.split(b'\n', 1)
            decoded = line_bytes.decode('utf-8', errors='replace') + '\n'
            output.append(decoded)
            log_to_stderr(f"[stderr] {decoded}")

    return "".join(output)


async def monitor_websocket(
    notifier: WebSocketNotifier,
    process: asyncio.subprocess.Process,
    job_id: str,
    max_reconnect_retries: int = 5
) -> None:
    """
    Surveille la connexion WebSocket et tente une reconnexion si elle se ferme.
    Ne tue le processus Claude que si la reconnexion échoue après plusieurs tentatives.

    Args:
        notifier: Le WebSocketNotifier (contient le websocket et peut reconnecter)
        process: Le processus Claude à surveiller
        job_id: ID du job pour les logs
        max_reconnect_retries: Nombre max de tentatives de reconnexion
    """
    from websockets.protocol import State

    while True:
        try:
            # Vérifier que le websocket est disponible
            if notifier.ws is None:
                log_to_stderr(f"\n⚠️ [Job {job_id}] WebSocket is None, attempting reconnect...\n")
                if not await notifier.reconnect(max_retries=max_reconnect_retries):
                    break  # Reconnexion échouée, sortir pour kill
                continue

            # Attendre un message (côté serveur peut envoyer des pings ou fermer)
            try:
                msg = await asyncio.wait_for(notifier.ws.recv(), timeout=60)
                # Traiter les pings du serveur
                try:
                    data = json.loads(msg) if msg else {}
                    if data.get("type") == "ping":
                        await notifier.ws.send(json.dumps({"type": "pong"}))
                except (json.JSONDecodeError, Exception):
                    pass

            except asyncio.TimeoutError:
                # Pas de message depuis 60s, vérifier l'état
                if notifier.ws and notifier.ws.state != State.OPEN:
                    log_to_stderr(f"\n⚠️ [Job {job_id}] WebSocket state: {notifier.ws.state.name}\n")
                    # Tenter reconnexion
                    if not await notifier.reconnect(max_retries=max_reconnect_retries):
                        break  # Reconnexion échouée
                continue

        except websockets.exceptions.ConnectionClosed as e:
            log_to_stderr(f"\n⚠️ [Job {job_id}] WebSocket disconnected (code={e.code}): {e.reason}\n")
            log_to_stderr(f"🔄 [Job {job_id}] Attempting reconnection...\n")

            # Tenter reconnexion au lieu de tuer
            if await notifier.reconnect(max_retries=max_reconnect_retries):
                log_to_stderr(f"✅ [Job {job_id}] Reconnected, continuing monitoring\n")
                continue
            else:
                log_to_stderr(f"❌ [Job {job_id}] Reconnection failed after {max_reconnect_retries} attempts\n")
                break  # Sortir pour kill

        except asyncio.CancelledError:
            # Tâche annulée (processus terminé normalement)
            log_to_stderr(f"\n[Job {job_id}] WebSocket monitor cancelled (process completed)\n")
            return  # Ne pas tuer

        except Exception as e:
            log_to_stderr(f"\n⚠️ [Job {job_id}] WebSocket monitor error: {type(e).__name__}: {e}\n")
            # Pour les autres erreurs, tenter une reconnexion
            if await notifier.reconnect(max_retries=max_reconnect_retries):
                continue
            break

    # Arrivé ici = reconnexion impossible après max_retries
    # Tuer le processus pour économiser les tokens
    if process.returncode is None:
        log_to_stderr(f"\n🛑 [Job {job_id}] Killing Claude process (reconnection failed)...\n")
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            log_to_stderr(f"\n🛑 [Job {job_id}] Force killing Claude process...\n")
            process.kill()
            await process.wait()
        log_to_stderr(f"\n✅ [Job {job_id}] Claude process terminated.\n")


async def launch_claude_stream_json(
    prompt: str,
    request,
    working_dir: Path,
    max_timeout: int = 7200,
    verbosity: int = 1,
    ws_url: str = None
) -> dict:
    """
    Lance Claude en mode stream-json avec architecture async native.

    Args:
        prompt: Le prompt complet à envoyer à Claude
        request: L'objet request contenant les infos du job
        working_dir: Répertoire de travail (worktree) pour Claude
        max_timeout: Timeout maximum en secondes (défaut: 2 heures)
        verbosity: Niveau de verbosité (0=minimal, 1=normal, 2=debug)
        ws_url: URL du serveur WebSocket (optionnel, utilise CRE_WS_URL env par défaut)

    Returns:
        dict avec 'success', 'result', 'cost', 'messages'
    """
    # Utiliser la configuration si ws_url non spécifié
    if ws_url is None:
        ws_url = f"{WS_BASE_URL}/api/ws/jobs"

    cmd = [
        "claude",
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose"
    ]

    # Variable pour tracker la tâche de monitoring
    ws_monitor_task = None

    try:
        log_to_stderr(f"🚀 Starting Claude (stream-json) in {working_dir}...\n")

        # Connexion WebSocket avec timeout
        async with asyncio.timeout(60):
            websocket = await websockets.connect(ws_url + f"/{request.jobId}")

        # Attendre le message "connected" du serveur (avec timeout séparé)
        async with asyncio.timeout(10):
            connected_msg = await websocket.recv()
            connected_data = json.loads(connected_msg)
            if connected_data.get("type") != "connected":
                log_to_stderr(f"⚠️ Expected 'connected' message, got: {connected_data.get('type')}\n")
            else:
                log_to_stderr(f"✅ WebSocket connected: {connected_data.get('message', '')}\n")

        async with websocket:
            # Créer le notifier avec les infos pour reconnexion
            notifier = WebSocketNotifier(websocket, ws_url=ws_url, job_id=request.jobId)
            processor = ClaudeEventProcessor(notifier, verbosity, working_dir)

            try:
                # Démarrer l'action
                await notifier.action_started()
                await notifier.step_started("setup")
                await notifier.step_log("Initializing Claude stream-json...")

                # Lancer le processus Claude
                # Note: on utilise read() par chunks dans read_stream/read_stderr
                # au lieu de readline(), donc 'limit' n'est plus critique.
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=dict(os.environ),  # Hérite du PATH complet (fnm, nvm, etc.)
                    cwd=working_dir,  # Worktree isolé pour ce commit
                )
                # Les phases (phase1, phase2_risk, etc.) démarrent automatiquement
                # quand les agents Task sont détectés dans _handle_tool_use
                # Le step_complete de setup est appelé par transition_to() lors du premier agent

                # Démarrer la tâche de monitoring WebSocket avec reconnexion automatique
                # Cette tâche tentera de reconnecter si le WebSocket se ferme
                # Ne tuera le processus que si la reconnexion échoue après plusieurs tentatives
                ws_monitor_task = asyncio.create_task(
                    monitor_websocket(notifier, process, request.jobId)
                )
                notifier.monitor_task = ws_monitor_task

                ws_disconnected = False  # Flag pour détecter si le WS a causé l'arrêt

                try:
                    # Lire stdout et stderr en parallèle avec timeout
                    async with asyncio.timeout(max_timeout):
                        await asyncio.gather(
                            read_stream(process.stdout, processor),
                            read_stderr(process.stderr)
                        )
                        await process.wait()

                except asyncio.TimeoutError:
                    log_to_stderr(f"\n⏱️ Timeout atteint ({max_timeout}s)\n")
                    await notifier.step_log(f"Timeout after {max_timeout}s", "stderr")
                    await notifier.step_complete("failure", f"Timeout after {max_timeout}s")
                    await notifier.action_complete()
                    process.kill()
                    await process.wait()

                    return {
                        "success": False,
                        "result": processor.result_text,
                        "cost": processor.total_cost,
                        "messages": processor.messages,
                        "error": f"Timeout after {max_timeout}s"
                    }

                finally:
                    # Annuler la tâche de monitoring (plus besoin si le processus est fini)
                    if ws_monitor_task and not ws_monitor_task.done():
                        ws_monitor_task.cancel()
                        try:
                            await ws_monitor_task
                        except asyncio.CancelledError:
                            pass
                    # Vérifier si le WebSocket s'est déconnecté
                    from websockets.protocol import State
                    if websocket.state != State.OPEN:
                        ws_disconnected = True

                # Vérifier si le processus a été tué à cause de la déconnexion WebSocket
                if ws_disconnected and process.returncode != 0:
                    log_to_stderr(f"\n⚠️ Process terminated due to WebSocket disconnection\n")
                    return {
                        "success": False,
                        "result": processor.result_text,
                        "cost": processor.total_cost,
                        "messages": processor.messages,
                        "error": "WebSocket disconnected - process terminated to save tokens"
                    }

                # Finaliser si pas encore fait
                if not notifier.action_completed:
                    if notifier.current_step:
                        await notifier.step_complete(notifier.action_status, "Process completed")
                    await notifier.action_complete()

                return {
                    "success": process.returncode == 0,
                    "result": processor.result_text,
                    "cost": processor.total_cost,
                    "messages": processor.messages,
                    "returncode": process.returncode
                }

            except Exception as e:
                # Erreur pendant l'exécution avec WebSocket connecté
                error_msg = f"{type(e).__name__}: {e}"
                log_to_stderr(f"\n❌ Execution error: {error_msg}\n")
                await notifier.step_log(f"Error: {error_msg}", "stderr")
                await notifier.step_complete("failure", f"Error: {error_msg}")
                await notifier.action_complete()

                # Nettoyer la tâche de monitoring si elle existe
                if ws_monitor_task and not ws_monitor_task.done():
                    ws_monitor_task.cancel()
                    try:
                        await ws_monitor_task
                    except asyncio.CancelledError:
                        pass

                raise  # Re-raise pour être capturé par le handler externe

    except websockets.exceptions.WebSocketException as e:
        log_to_stderr(f"\n❌ WebSocket error: {e}\n")
        return {
            "success": False,
            "result": "",
            "cost": 0.0,
            "messages": [],
            "error": f"WebSocket error: {e}"
        }

    except FileNotFoundError as e:
        # Claude CLI non trouvé
        error_msg = f"Claude CLI not found: {e}"
        log_to_stderr(f"\n❌ {error_msg}\n")
        try:
            async with websockets.connect(ws_url + f"/{request.jobId}") as ws:
                notifier = WebSocketNotifier(ws)
                await notifier.action_started()
                await notifier.fail_with_error(error_msg)
        except Exception:
            pass  # Best effort
        return {
            "success": False,
            "result": "",
            "cost": 0.0,
            "messages": [],
            "error": error_msg
        }

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        log_to_stderr(f"\n❌ Error: {error_msg}\n")
        try:
            async with websockets.connect(ws_url + f"/{request.jobId}") as ws:
                notifier = WebSocketNotifier(ws)
                await notifier.action_started()
                await notifier.fail_with_error(error_msg)
        except Exception:
            pass  # Best effort
        return {
            "success": False,
            "result": "",
            "cost": 0.0,
            "messages": [],
            "error": str(e)
        }


# =============================================================================
# Note: launch_claude_process() supprimé
# Utiliser launch_claude_stream_json() directement avec working_dir depuis main.py
# =============================================================================
