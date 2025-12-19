# claude.py
"""
Module pour lancer Claude Code de manière programmatique avec streaming des logs.
"""

import subprocess
import pty
import os
import sys
import select
import re
import time
import fcntl
import struct
import termios
import json
from pathlib import Path
from typing import Callable, Optional
import asyncio
import websockets
import threading

def log_to_stderr(text: str):
    """Log vers stderr pour voir en temps réel dans le terminal."""
    sys.stderr.write(text)
    sys.stderr.flush()

def switch_branch(branch_name: str) -> bool:
    """Change de branche git."""
    print(f"Switching to branch: {branch_name}\n")
    result = subprocess.run(
        ["git", "checkout", branch_name],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    return result.returncode == 0


def strip_ansi(text: str) -> str:
    """Supprime les séquences ANSI de contrôle (couleurs, curseur, etc.)."""
    # Séquences CSI (Control Sequence Introducer)
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    text = ansi_escape.sub('', text)
    # Séquences OSC (Operating System Command)
    text = re.sub(r'\x1B\].*?(?:\x07|\x1B\\)', '', text)
    # Autres séquences d'échappement
    text = re.sub(r'\x1B[()][AB012]', '', text)
    text = re.sub(r'\x1B[@-_]', '', text)
    # Caractères de contrôle restants (sauf newline et tab)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', text)
    return text

async def wb_client(type:str, jobId: str):
    print(f"Starting websocket client jobId {jobId}...\n")
    async with websockets.connect(f"ws://cre-interface-host:8080/api/ws/jobs/{jobId}") as websocket:
        while True:
            message = {
                "type": "action_started",
                "steps": ["setup", "compile", "test", "package"]
            }
            await websocket.send(message)

async def launch_claude_stream_json(
    prompt: str,
    request,
    max_timeout: int = 1800,
    verbosity: int = 1,
    show_tool_results: bool = True
) -> dict:
    """
    Lance Claude en mode stream-json pour un parsing propre des événements.

    Args:
        prompt: Le prompt complet à envoyer à Claude
        log_callback: Fonction appelée pour chaque message de log
        max_timeout: Timeout maximum en secondes (défaut: 30 minutes)
        verbosity: Niveau de verbosité (0=minimal, 1=normal, 2=debug JSON)
        show_tool_results: Si True, affiche les résultats des outils

    Returns:
        dict avec 'success', 'result', 'cost', 'messages'
    """

    def log(msg: str):
        if log_to_stderr:
            log_to_stderr(msg)

    messages = []
    result_text = ""
    total_cost = 0.0
    current_step = None
    action_status = "success"  # Sera mis à "failure" si une étape échoue
    action_completed = False  # Pour éviter d'envoyer action_complete plusieurs fois

    cmd = [
        "claude",
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose"
    ]

    try:
        log("    (stream-json)...\n")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )

        start_time = time.time()

        async with websockets.connect(f"ws://localhost:8765") as websocket:

            # Helper functions for WebSocket messages
            async def send_action_started(steps: list):
                await websocket.send(json.dumps({
                    "type": "action_started",
                    "steps": steps
                }))

            async def send_step_started(step: str):
                nonlocal current_step
                current_step = step
                await websocket.send(json.dumps({
                    "type": "step_started",
                    "step": step
                }))

            async def send_step_log(step: str, line: str, stream: str = "stdout"):
                await websocket.send(json.dumps({
                    "type": "step_log",
                    "step": step,
                    "line": line,
                    "stream": stream
                }))

            async def send_step_complete(step: str, status: str, output: str = ""):
                nonlocal action_status
                if status == "failure":
                    action_status = "failure"
                await websocket.send(json.dumps({
                    "type": "step_complete",
                    "step": step,
                    "status": status,
                    "output": output
                }))

            async def send_action_complete(status: str):
                nonlocal action_completed
                if action_completed:
                    return  # Déjà envoyé
                action_completed = True
                await websocket.send(json.dumps({
                    "type": "action_complete",
                    "status": status
                }))

            # Envoyer action_started avec les étapes
            await send_action_started(["setup", "analyze", "tools", "synthesis"])
            print("Sending websocket message...\n")

            # Démarrer l'étape setup
            await send_step_started("setup")
            await send_step_log("setup", "Initializing Claude stream-json...", "stdout")
            await send_step_complete("setup", "success", "Setup completed")

            # Démarrer l'étape analyze
            await send_step_started("analyze")

            while True:

                # Vérifier timeout
                if time.time() - start_time > max_timeout:
                    log(f"\nTimeout maximum atteint ({max_timeout}s)\n")
                    if current_step:
                        await send_step_log(current_step, f"Timeout after {max_timeout}s", "stderr")
                        await send_step_complete(current_step, "failure", f"Timeout after {max_timeout}s")
                    await send_action_complete("failure")
                    process.kill()
                    break

                # Utiliser select pour éviter le blocage
                if process.stdout:
                    readable, _, _ = select.select([process.stdout], [], [], 1.0)

                    if readable:
                        line = process.stdout.readline()
                        if not line:
                            # Fin du stdout - compléter si pas encore fait
                            if current_step and not action_completed:
                                await send_step_complete(current_step, action_status, "Stream completed")
                                await send_action_complete(action_status)
                            break

                        line = line.strip()
                        if not line:
                            continue

                        try:
                            event = json.loads(line)
                            event_type = event.get("type", "")

                            # Mode debug (verbosity=2): affiche les événements JSON bruts
                            if verbosity >= 2:
                                log(f"\n[DEBUG] {event_type}: {json.dumps(event, ensure_ascii=False)[:500]}\n")

                            if event_type == "assistant":
                                # Message de l'assistant
                                msg = event.get("message", {})
                                content = msg.get("content", [])
                                for block in content:
                                    if block.get("type") == "text":
                                        text = block.get("text", "")
                                        result_text += text
                                        log(text)
                                        # Envoyer step_log pour le texte de l'assistant
                                        if current_step:
                                            await send_step_log(current_step, text.strip(), "stdout")
                                    elif block.get("type") == "tool_use":
                                        tool_name = block.get("name", "unknown")
                                        tool_input = block.get("input", {})

                                        # Passer à l'étape tools si on n'y est pas déjà
                                        if current_step != "tools":
                                            if current_step == "analyze":
                                                await send_step_complete("analyze", "success", "Analysis completed")
                                            await send_step_started("tools")

                                        tool_log = f"🔧 Tool: {tool_name}"
                                        log(f"\n╭─ 🔧 Tool: {tool_name}\n")
                                        if tool_name == "Bash":
                                            cmd_str = tool_input.get("command", "")
                                            desc = tool_input.get("description", "")
                                            if desc:
                                                log(f"│  📝 {desc}\n")
                                                tool_log += f" - {desc}"
                                            log(f"│  $ {cmd_str[:200]}{'...' if len(cmd_str) > 200 else ''}\n")
                                        elif tool_name == "Read":
                                            log(f"│  📄 {tool_input.get('file_path', '')}\n")
                                            tool_log += f" - {tool_input.get('file_path', '')}"
                                        elif tool_name == "Edit":
                                            log(f"│  ✏️  {tool_input.get('file_path', '')}\n")
                                            tool_log += f" - {tool_input.get('file_path', '')}"
                                        elif tool_name == "Write":
                                            log(f"│  📝 {tool_input.get('file_path', '')}\n")
                                            tool_log += f" - {tool_input.get('file_path', '')}"
                                        elif tool_name == "Grep":
                                            log(f"│  🔍 Pattern: {tool_input.get('pattern', '')}\n")
                                            tool_log += f" - Pattern: {tool_input.get('pattern', '')}"
                                        elif tool_name == "Glob":
                                            log(f"│  📂 Pattern: {tool_input.get('pattern', '')}\n")
                                            tool_log += f" - Pattern: {tool_input.get('pattern', '')}"
                                        else:
                                            # Autres outils: afficher l'input complet
                                            log(f"│  Input: {json.dumps(tool_input, ensure_ascii=False)[:300]}\n")
                                        log(f"╰─\n")
                                        await send_step_log("tools", tool_log, "stdout")
                                    elif block.get("type") == "thinking":
                                        # Bloc de réflexion (extended thinking)
                                        thinking_text = block.get("thinking", "")
                                        log(f"\n💭 [Thinking]: {thinking_text[:500]}{'...' if len(thinking_text) > 500 else ''}\n")
                                        if current_step:
                                            await send_step_log(current_step, f"[Thinking] {thinking_text[:200]}", "stdout")

                            elif event_type == "content_block_start":
                                # Début d'un bloc de contenu
                                block = event.get("content_block", {})
                                block_type = block.get("type", "")
                                if block_type == "tool_use":
                                    tool_name = block.get("name", "")
                                    log(f"\n⏳ Starting tool: {tool_name}...\n")
                                elif block_type == "thinking":
                                    log(f"\n💭 [Claude réfléchit...]\n")

                            elif event_type == "content_block_delta":
                                # Streaming de contenu
                                delta = event.get("delta", {})
                                delta_type = delta.get("type", "")
                                if delta_type == "text_delta":
                                    text = delta.get("text", "")
                                    result_text += text
                                    log(text)
                                elif delta_type == "thinking_delta":
                                    # Streaming de la réflexion
                                    thinking = delta.get("thinking", "")
                                    log(f"💭 {thinking}")
                                elif delta_type == "input_json_delta":
                                    # Streaming de l'input d'un outil
                                    partial = delta.get("partial_json", "")
                                    # On peut choisir de ne pas l'afficher car c'est partiel
                                    pass

                            elif event_type == "content_block_stop":
                                # Fin d'un bloc - on peut ajouter un marqueur
                                pass

                            elif event_type == "tool_result":
                                # Résultat d'un outil (user message contenant le résultat)
                                pass  # Généralement traité via "user" event

                            elif event_type == "user":
                                # Message utilisateur (souvent les résultats d'outils)
                                if show_tool_results:
                                    msg = event.get("message", {})
                                    content = msg.get("content", [])
                                    for block in content:
                                        if block.get("type") == "tool_result":
                                            tool_use_id = block.get("tool_use_id", "")
                                            tool_content = block.get("content", "")
                                            is_error = block.get("is_error", False)

                                            # Tronquer si trop long
                                            if isinstance(tool_content, str) and len(tool_content) > 500:
                                                display_content = tool_content[:500] + "..."
                                            else:
                                                display_content = str(tool_content)[:500]

                                            if is_error:
                                                log(f"\n❌ Tool Error: {display_content}\n")
                                                await send_step_log("tools", f"❌ Error: {display_content}", "stderr")
                                            else:
                                                log(f"\n✅ Tool Result: {display_content}\n")
                                                await send_step_log("tools", f"✅ Result: {display_content[:200]}", "stdout")

                            elif event_type == "system":
                                # Message système
                                msg = event.get("message", {})
                                subtype = event.get("subtype", "")
                                log(f"\n🔔 [System - {subtype}]\n")
                                if current_step:
                                    await send_step_log(current_step, f"[System] {subtype}", "stdout")

                            elif event_type == "result":
                                # Résultat final
                                total_cost = event.get("cost_usd", 0.0)
                                log(f"\n\nCost: ${total_cost:.4f}\n")

                                # Compléter l'étape en cours et passer à synthesis
                                if current_step == "tools":
                                    await send_step_complete("tools", "success", "Tools execution completed")
                                elif current_step == "analyze":
                                    await send_step_complete("analyze", "success", "Analysis completed")

                                await send_step_started("synthesis")
                                await send_step_log("synthesis", f"Generating final result (Cost: ${total_cost:.4f})", "stdout")
                                await send_step_complete("synthesis", "success", f"## Result\n\n{result_text[:1000]}")
                                await send_action_complete(action_status)

                            elif event_type == "error":
                                error_msg = event.get("error", {}).get("message", "Unknown error")
                                log(f"\nErreur: {error_msg}\n")
                                # Envoyer l'erreur au step actuel
                                if current_step:
                                    await send_step_log(current_step, f"Error: {error_msg}", "stderr")
                                    await send_step_complete(current_step, "failure", f"## Error\n\n{error_msg}")
                                await send_action_complete("failure")

                            messages.append(event)

                        except json.JSONDecodeError:
                            # Ligne non-JSON, probablement du debug
                            log(f"{line}\n")

                # Vérifier si le process est terminé
                if process.poll() is not None:
                    # Lire les lignes restantes
                    if process.stdout:
                        for line in process.stdout:
                            line = line.strip()
                            if line:
                                try:
                                    messages.append(json.loads(line))
                                except:
                                    pass
                    # Compléter le step en cours si pas encore fait
                    if current_step and not action_completed:
                        await send_step_complete(current_step, action_status, "Process completed")
                        await send_action_complete(action_status)
                    break

        # Lire stderr
        if process.stderr:
            stderr_output = process.stderr.read()
            if stderr_output:
                log(f"\n[stderr]: {stderr_output}\n")

        process.wait()

        return {
            "success": process.returncode == 0,
            "result": result_text,
            "cost": total_cost,
            "messages": messages,
            "returncode": process.returncode
        }

    except Exception as e:
        log(f"\nErreur: {type(e).__name__}: {e}\n")
        return {
            "success": False,
            "result": "",
            "cost": 0.0,
            "messages": [],
            "error": str(e)
        }


def launch_claude_pty(
    prompt: str,
    log_callback: Optional[Callable[[str], None]] = None,
    idle_timeout: int = 120,
    max_timeout: int = 1800
) -> str:
    """
    Lance Claude avec un PTY pour capturer la sortie formatée en temps réel.
    Utile pour voir le rendu "humain" avec les couleurs (nettoyées).

    Args:
        prompt: Le prompt complet à envoyer à Claude
        log_callback: Fonction appelée pour chaque chunk de sortie
        idle_timeout: Secondes d'inactivité avant de considérer terminé
        max_timeout: Timeout maximum total (défaut: 30 minutes)

    Returns:
        La sortie complète de Claude (nettoyée des codes ANSI)
    """

    def log(msg: str):
        if log_callback:
            log_callback(msg)

    # Créer un pseudo-terminal
    master_fd, slave_fd = pty.openpty()

    # Configurer les dimensions du terminal
    winsize = struct.pack('HHHH', 50, 200, 0, 0)
    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

    full_output = []
    process = None

    try:
        cmd = [
            "claude",
            "-p", prompt,
            "--dangerously-skip-permissions"
        ]

        process = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            env={**os.environ, "TERM": "xterm-256color"}
        )

        os.close(slave_fd)
        slave_fd = -1

        log("Lancement de Claude (PTY)...\n")

        # Rendre non-bloquant
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        start_time = time.time()
        last_data_time = time.time()

        while True:
            elapsed = time.time() - start_time
            idle_time = time.time() - last_data_time

            if elapsed > max_timeout:
                log(f"\nTimeout maximum atteint ({max_timeout}s)\n")
                break

            if idle_time > idle_timeout:
                log(f"\nFin détectée (inactivité de {idle_timeout}s)\n")
                break

            if process.poll() is not None:
                # Lire les données restantes
                time.sleep(0.2)
                try:
                    remaining = os.read(master_fd, 65536).decode('utf-8', errors='replace')
                    if remaining:
                        clean = strip_ansi(remaining)
                        full_output.append(clean)
                        log(clean)
                except:
                    pass
                log("\nProcess Claude terminé\n")
                break

            try:
                readable, _, _ = select.select([master_fd], [], [], 0.5)
            except select.error:
                break

            if readable:
                try:
                    data = os.read(master_fd, 4096).decode('utf-8', errors='replace')
                    if data:
                        clean = strip_ansi(data)
                        full_output.append(clean)
                        log(clean)
                        last_data_time = time.time()
                except BlockingIOError:
                    pass
                except OSError as e:
                    if e.errno == 5:  # Input/output error
                        break
                    raise

    except Exception as e:
        log(f"\nErreur: {type(e).__name__}: {e}\n")
        import traceback
        log(traceback.format_exc())

    finally:
        if slave_fd != -1:
            try:
                os.close(slave_fd)
            except:
                pass

        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                try:
                    process.kill()
                except:
                    pass

        try:
            os.close(master_fd)
        except:
            pass

    return "".join(full_output)


def launch_claude_process(
    request,
    verbosity: int = 1
) -> None:
    """
    Lance Claude avec le prompt d'analyse (analyze_py.md).

    Args:
        log_callback: Fonction pour le streaming des logs (optionnel)
        use_stream_json: Utiliser le mode stream-json (recommandé) ou PTY
        verbosity: Niveau de verbosité (0=minimal, 1=normal, 2=debug JSON)

    Returns:
        La sortie complète ou le résultat
    """
    prompt_path = Path(".claude/commands/analyze_py.md")

    if not prompt_path.exists():
        print(f"Fichier prompt non trouvé: {prompt_path}")
        return None

    prompt = prompt_path.read_text()

    if (request.action == 'issue_detector'):
        asyncio.run(launch_claude_stream_json(
            prompt=prompt,
            request=request,
            max_timeout=1800,
            verbosity=verbosity
        ))
