# main.py
"""
API FastAPI pour déclencher les analyses Claude.
"""

import asyncio
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime, timedelta, timezone
from enum import Enum

import json
import websockets
import yaml

from claude import launch_claude_stream_json, log_to_stderr, WebSocketNotifier, WS_BASE_URL

# Charger .env si présent (avant les autres imports qui utilisent les env vars)
from dotenv import load_dotenv
load_dotenv()

# Mode test activé via TEST_MODE=1
TEST_MODE = os.environ.get("TEST_MODE", "0") == "1"

# Import du gestionnaire de worktrees
import sys
sys.path.insert(0, str(Path(__file__).parent / ".claude"))
sys.path.insert(0, str(Path(__file__).parent / ".claude" / "scripts"))
from worktree import WorktreeManager, async_cleanup_expired

# Import du validateur d'issues (optionnel)
try:
    from validate_issues import IssueValidator, ValidationConfig, ReportValidationResult
    VALIDATOR_AVAILABLE = True
except ImportError:
    VALIDATOR_AVAILABLE = False


# =============================================================================
# Git Utilities
# =============================================================================

# Extensions de code à analyser
CODE_EXTENSIONS = ['.c', '.cpp', '.h', '.hpp', '.py', '.js', '.ts', '.tsx', '.go', '.rs', '.java']


# =============================================================================
# SonarCloud Integration
# =============================================================================

SONAR_CONFIG_PATH = Path(__file__).parent / ".claude" / "config" / "sonar.yaml"
SONARCLOUD_API_URL = "https://sonarcloud.io/api"


def load_sonar_config() -> dict:
    """Charge la configuration SonarCloud depuis sonar.yaml."""
    if SONAR_CONFIG_PATH.exists():
        with open(SONAR_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def get_sonar_project_key() -> str | None:
    """Récupère la clé projet SonarCloud depuis env ou config."""
    # Priorité: variable d'environnement
    env_key = os.environ.get("SONAR_PROJECT_KEY")
    if env_key:
        return env_key

    # Fallback: config yaml (si pas de placeholder)
    config = load_sonar_config()
    config_key = config.get("sonarcloud", {}).get("project_key", "")
    if config_key and not config_key.startswith("$"):
        return config_key

    return None


def get_sonar_token() -> str | None:
    """Récupère le token SonarCloud depuis l'environnement."""
    return os.environ.get("SONAR_TOKEN")


def format_date_for_sonar(dt: datetime) -> str:
    """Formate une date pour l'API SonarCloud (ISO 8601)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+0000")


def get_commit_date(commit_sha: str, cwd: Path = None) -> datetime | None:
    """Récupère la date d'un commit."""
    success, date_str = run_git_command(
        ['show', '-s', '--format=%cI', commit_sha],
        cwd=cwd
    )
    if success and date_str:
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            pass
    return None


async def fetch_sonar_issues(
    git_context: 'GitContext',
    output_path: Path,
    branch_name: str,
) -> dict | None:
    """
    Fetch les issues SonarCloud pour le contexte git donné.

    Utilise automatiquement:
    - La branche du contexte
    - La date du from_commit (merge-base) comme createdAfter

    Args:
        git_context: Contexte git résolu
        output_path: Chemin du fichier JSON de sortie
        branch_name: Nom de la branche

    Returns:
        Dict avec les issues ou None si erreur/pas configuré
    """
    project_key = get_sonar_project_key()
    token = get_sonar_token()

    if not project_key:
        log_to_stderr("[SonarCloud] SONAR_PROJECT_KEY non configuré, skip\n")
        return None

    if not token:
        log_to_stderr("[SonarCloud] SONAR_TOKEN non configuré, skip\n")
        return None

    # Charger la config
    config = load_sonar_config()
    defaults = config.get("sonarcloud", {}).get("defaults", {})
    auto_filter = config.get("sonarcloud", {}).get("auto_filter", {})

    # Construire les paramètres
    params = {
        "projectKeys": project_key,
        "ps": defaults.get("page_size", 500),
        "p": 1,
        "branch": branch_name,
        "statuses": defaults.get("statuses", "OPEN,CONFIRMED,REOPENED"),
    }

    # Types
    types = defaults.get("types")
    if types:
        params["types"] = types

    # Filtrage par date basé sur le merge-base
    if auto_filter.get("use_leak_period", False):
        params["sinceLeakPeriod"] = "true"
    elif auto_filter.get("use_merge_base_date", True):
        # Utiliser la date du from_commit (merge-base)
        merge_base_date = get_commit_date(git_context.from_commit)
        if merge_base_date:
            params["createdAfter"] = format_date_for_sonar(merge_base_date)
            log_to_stderr(f"[SonarCloud] Filtrage depuis merge-base: {params['createdAfter']}\n")
        else:
            # Fallback
            fallback = auto_filter.get("fallback_since", "7d")
            if fallback.endswith("d"):
                days = int(fallback[:-1])
                since = datetime.now(timezone.utc) - timedelta(days=days)
                params["createdAfter"] = format_date_for_sonar(since)

    # Construire l'URL
    url = f"{SONARCLOUD_API_URL}/issues/search?{urlencode(params)}"

    log_to_stderr(f"[SonarCloud] Fetching issues...\n")
    log_to_stderr(f"[SonarCloud] Project: {project_key}\n")
    log_to_stderr(f"[SonarCloud] Branch: {branch_name}\n")

    # Exécuter curl (en async via subprocess)
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "-u", f"{token}:", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        if proc.returncode != 0:
            log_to_stderr(f"[SonarCloud] Erreur curl: {stderr.decode()}\n")
            return None

        data = json.loads(stdout.decode())

        # Pagination: si plus de 500 issues, fetch les autres pages
        total = data.get("total", 0)
        if total > 500:
            log_to_stderr(f"[SonarCloud] {total} issues, pagination...\n")
            all_issues = data.get("issues", [])
            all_rules = {r.get("key"): r for r in data.get("rules", [])}
            all_components = {c.get("key"): c for c in data.get("components", [])}

            page = 2
            while len(all_issues) < total:
                params["p"] = page
                page_url = f"{SONARCLOUD_API_URL}/issues/search?{urlencode(params)}"

                proc = await asyncio.create_subprocess_exec(
                    "curl", "-s", "-u", f"{token}:", page_url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
                page_data = json.loads(stdout.decode())

                issues = page_data.get("issues", [])
                if not issues:
                    break

                all_issues.extend(issues)
                for r in page_data.get("rules", []):
                    all_rules[r.get("key")] = r
                for c in page_data.get("components", []):
                    all_components[c.get("key")] = c

                page += 1

            data = {
                "total": len(all_issues),
                "issues": all_issues,
                "rules": list(all_rules.values()),
                "components": list(all_components.values()),
            }

        # Sauvegarder le résultat
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        issues_count = len(data.get("issues", []))
        log_to_stderr(f"[SonarCloud] {issues_count} issues récupérées -> {output_path}\n")

        return data

    except asyncio.TimeoutError:
        log_to_stderr("[SonarCloud] Timeout lors du fetch\n")
        return None
    except json.JSONDecodeError as e:
        log_to_stderr(f"[SonarCloud] JSON invalide: {e}\n")
        return None
    except Exception as e:
        log_to_stderr(f"[SonarCloud] Erreur: {e}\n")
        return None


async def transform_sonar_report(
    issues_json_path: Path,
    output_dir: Path,
    commit: str,
    branch: str,
    files_filter: list[str] | None = None,
) -> Path | None:
    """
    Transforme le JSON SonarCloud en rapport Markdown.

    Args:
        issues_json_path: Chemin du fichier JSON des issues
        output_dir: Dossier de sortie
        commit: Hash du commit
        branch: Nom de la branche
        files_filter: Liste de fichiers pour filtrer (mode diff)

    Returns:
        Chemin du rapport MD ou None si erreur
    """
    transform_script = Path(__file__).parent / ".claude" / "scripts" / "transform-sonar.py"

    if not transform_script.exists():
        log_to_stderr(f"[SonarCloud] Script transform-sonar.py introuvable\n")
        return None

    if not issues_json_path.exists():
        log_to_stderr(f"[SonarCloud] Fichier issues introuvable: {issues_json_path}\n")
        return None

    output_md = output_dir / "sonar.md"

    cmd = [
        "python", str(transform_script),
        str(issues_json_path),
        "-o", str(output_md),
        "-c", commit,
        "-b", branch,
    ]

    # Ajouter le filtre de fichiers si présent
    if files_filter:
        cmd.extend(["-f", ",".join(files_filter)])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if stderr:
            log_to_stderr(f"[SonarCloud] Transform output:\n{stderr.decode()}\n")

        if output_md.exists():
            log_to_stderr(f"[SonarCloud] Rapport généré: {output_md}\n")
            return output_md
        else:
            log_to_stderr(f"[SonarCloud] Rapport non généré\n")
            return None

    except Exception as e:
        log_to_stderr(f"[SonarCloud] Erreur transform: {e}\n")
        return None


# =============================================================================
# Report Validation
# =============================================================================

def validate_report(report_path: Path, strict: bool = False) -> dict | None:
    """
    Valide la qualité d'un rapport d'issues.

    Args:
        report_path: Chemin vers le fichier JSON du rapport
        strict: Utiliser le mode strict (longueurs minimales plus élevées)

    Returns:
        Dict avec les résultats de validation ou None si validateur non disponible
    """
    if not VALIDATOR_AVAILABLE:
        log_to_stderr("[Validation] Validateur non disponible\n")
        return None

    if not report_path.exists():
        log_to_stderr(f"[Validation] Fichier introuvable: {report_path}\n")
        return None

    # Configurer le validateur
    config = ValidationConfig()
    if strict:
        config.min_where_length = 300
        config.min_why_length = 400
        config.min_how_length = 300

    validator = IssueValidator(config)
    result = validator.validate_report(report_path)

    log_to_stderr(f"[Validation] {result.valid_issues}/{result.total_issues} issues valides\n")
    if not result.is_valid:
        log_to_stderr(f"[Validation] Problèmes détectés:\n")
        for err_type, count in sorted(result.summary.items(), key=lambda x: -x[1])[:5]:
            log_to_stderr(f"  - {err_type}: {count}\n")

    return {
        "is_valid": result.is_valid,
        "total_issues": result.total_issues,
        "valid_issues": result.valid_issues,
        "invalid_issues": result.invalid_issues,
        "summary": result.summary
    }


@dataclass
class GitContext:
    """Contexte git résolu pour l'analyse."""
    from_commit: str
    to_commit: str
    from_commit_short: str
    to_commit_short: str
    parent_branch: str
    files_changed: list[str] = field(default_factory=list)
    stats: str = ""
    detection_mode: str = "auto"  # "auto" ou "manual"


def run_git_command(args: list[str], timeout: int = 60, cwd: Path = None) -> tuple[bool, str]:
    """
    Exécute une commande git et retourne (success, output).

    Args:
        args: Liste des arguments git (sans 'git')
        timeout: Timeout en secondes
        cwd: Répertoire de travail (optionnel, pour les worktrees)

    Returns:
        Tuple (success: bool, output: str)
    """
    try:
        result = subprocess.run(
            ['git'] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return result.returncode == 0, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "Git command timed out"
    except Exception as e:
        return False, str(e)


def _fallback_to_main_branch(commit_sha: str) -> tuple[str, str]:
    """Fallback vers main/develop/master si détection échoue."""
    for branch in ['main', 'develop', 'master']:
        success, _ = run_git_command(['rev-parse', '--verify', branch])
        if success:
            success, merge_base = run_git_command(['merge-base', commit_sha, branch])
            if success and merge_base:
                return branch, merge_base

    # Dernier recours: premier commit du repo
    success, first_commit = run_git_command(['rev-list', '--max-parents=0', 'HEAD'])
    return "unknown", first_commit if success else commit_sha


def is_branch_at_origin(branch_name: str) -> bool:
    """
    Vérifie si la branche locale est au même point que origin.
    Retourne True si origin/<branch> existe et pointe sur le même commit.
    """
    # Vérifier si origin/<branch> existe
    success, origin_sha = run_git_command(['rev-parse', f'origin/{branch_name}'])
    if not success:
        return False

    # Vérifier si la branche locale pointe sur le même commit
    success, local_sha = run_git_command(['rev-parse', branch_name])
    if not success:
        return False

    return origin_sha == local_sha


def get_first_commit() -> str | None:
    """
    Retourne le premier commit du repo (root commit).
    """
    success, first = run_git_command(['rev-list', '--max-parents=0', 'HEAD'])
    return first if success else None


def detect_parent_branch(commit_sha: str, current_branch: str) -> tuple[str, str]:
    """
    Détecte la branche parente avec le merge-base le plus proche.

    Algorithme:
    1. Lister toutes les branches locales
    2. Pour chaque branche, calculer le merge-base avec commit_sha
    3. Compter les commits entre merge-base et commit_sha
    4. La branche avec le moins de commits est la parente

    Args:
        commit_sha: Le commit cible
        current_branch: La branche actuelle (à exclure)

    Returns:
        Tuple (parent_branch: str, merge_base_commit: str)
    """
    # Liste des branches candidates
    success, branches_output = run_git_command(['branch', '--format=%(refname:short)'])
    if not success:
        return _fallback_to_main_branch(commit_sha)

    branches = [
        b.strip() for b in branches_output.split('\n')
        if b.strip() and b.strip() != current_branch
    ]

    # Priorité: main > develop > master (on les teste en premier)
    priority_branches = ['main', 'develop', 'master']
    ordered_branches = [b for b in priority_branches if b in branches]
    ordered_branches += [b for b in branches if b not in priority_branches]

    best_branch = None
    best_merge_base = None
    min_distance = float('inf')

    for branch in ordered_branches:
        # Calculer le merge-base
        success, merge_base = run_git_command(['merge-base', commit_sha, branch])
        if not success or not merge_base:
            continue

        # Compter les commits entre merge-base et commit_sha
        success, count_output = run_git_command([
            'rev-list', '--count', f'{merge_base}..{commit_sha}'
        ])
        if not success:
            continue

        try:
            distance = int(count_output)
        except ValueError:
            continue

        # La branche avec le moins de commits après le merge-base est la parente
        if distance < min_distance:
            min_distance = distance
            best_branch = branch
            best_merge_base = merge_base

    if best_branch and best_merge_base:
        return best_branch, best_merge_base

    return _fallback_to_main_branch(commit_sha)


def get_diff_between_commits(from_commit: str, to_commit: str) -> dict:
    """
    Calcule le diff entre deux commits.

    Args:
        from_commit: Commit de départ (exclus)
        to_commit: Commit de fin (inclus)

    Returns:
        Dict avec files_changed, stats, etc.
    """
    # Hash courts
    _, from_short = run_git_command(['rev-parse', '--short', from_commit])
    _, to_short = run_git_command(['rev-parse', '--short', to_commit])

    # git diff --name-status pour catégoriser les fichiers
    success, name_status = run_git_command([
        'diff', f'{from_commit}..{to_commit}', '--name-status'
    ])

    files_changed = []

    if success:
        for line in name_status.split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue

            status, filepath = parts[0], parts[1]

            # Vérifier l'extension
            ext = Path(filepath).suffix.lower()
            if ext not in CODE_EXTENSIONS:
                continue

            # On ignore les fichiers supprimés (status == 'D')
            if status != 'D':
                files_changed.append(filepath)

    # Stats
    _, stats = run_git_command([
        'diff', f'{from_commit}..{to_commit}', '--stat'
    ])

    return {
        'from_commit': from_commit,
        'to_commit': to_commit,
        'from_commit_short': from_short or from_commit[:7],
        'to_commit_short': to_short or to_commit[:7],
        'files_changed': files_changed,
        'stats': stats or ""
    }


def resolve_git_context(git_param: Optional[str], commit_sha: str, branch_name: str) -> GitContext:
    """
    Résout le contexte git selon le paramètre 'git'.

    Args:
        git_param: None ou "0" pour auto-détection, ou hash de commit
        commit_sha: Le commit cible (to_commit)
        branch_name: La branche actuelle

    Returns:
        GitContext avec toutes les informations nécessaires
    """
    if git_param is None or git_param == "0":
        # Cas spécial: branche principale sans divergence avec origin
        # (git show-branch -a montre que local et origin sont au même commit)
        main_branches = ['main', 'master', 'develop']
        if branch_name in main_branches and is_branch_at_origin(branch_name):
            # Utiliser le premier commit du repo pour analyser tout l'historique
            from_commit = get_first_commit()
            if not from_commit:
                raise ValueError("Cannot find first commit of repository")
            parent_branch = "root"
            detection_mode = "full-history"
        else:
            # Mode normal: Auto-détection de la branche parente
            parent_branch, from_commit = detect_parent_branch(commit_sha, branch_name)
            detection_mode = "auto"
    else:
        # Mode 2: Hash spécifié
        # Vérifier que le hash est valide
        success, _ = run_git_command(['rev-parse', '--verify', git_param])
        if not success:
            raise ValueError(f"Invalid git hash: {git_param}")

        from_commit = git_param
        parent_branch = "specified"
        detection_mode = "manual"

    # Calculer le diff
    diff_result = get_diff_between_commits(from_commit, commit_sha)

    return GitContext(
        from_commit=diff_result['from_commit'],
        to_commit=diff_result['to_commit'],
        from_commit_short=diff_result['from_commit_short'],
        to_commit_short=diff_result['to_commit_short'],
        parent_branch=parent_branch,
        files_changed=diff_result['files_changed'],
        stats=diff_result['stats'],
        detection_mode=detection_mode
    )


def build_analysis_prompt(git_context: GitContext, request) -> str:
    """
    Construit le prompt d'analyse avec le contexte git pré-calculé.

    Args:
        git_context: Contexte git résolu
        request: Requête originale

    Returns:
        Prompt complet pour Claude
    """
    prompt_path = Path(".claude/commands/analyse_py2.md")
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    template = prompt_path.read_text()

    # Préparer la liste des fichiers
    files_list = '\n'.join(f"  - {f}" for f in git_context.files_changed) if git_context.files_changed else "  (aucun fichier)"

    # Remplacer les placeholders
    replacements = {
        '$FROM_COMMIT': git_context.from_commit,
        '$TO_COMMIT': git_context.to_commit,
        '$FROM_COMMIT_SHORT': git_context.from_commit_short,
        '$TO_COMMIT_SHORT': git_context.to_commit_short,
        '$BRANCH_NAME': request.branchName,
        '$PARENT_BRANCH': git_context.parent_branch,
        '$FILES_LIST': files_list,
        '$FILES_COUNT': str(len(git_context.files_changed)),
        '$STATS': git_context.stats or "(pas de stats)",
        '$DETECTION_MODE': git_context.detection_mode,
    }

    for key, value in replacements.items():
        template = template.replace(key, value)

    return template


# =============================================================================
# Modèles
# =============================================================================

class JobStatus(str, Enum):
    """Statuts possibles d'un job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ClaudeRequest(BaseModel):
    """Requête pour lancer une analyse Claude."""
    jobId: str
    branchName: str
    commitSha: str
    action: Literal['build_i4gen', 'build_compact', 'issue_detector']
    lastAnalyzedCommit: Optional[str] = None  # null pour auto-détection branche parente, ou hash de commit


class JobInfo(BaseModel):
    """Informations sur un job."""
    jobId: str
    status: JobStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[dict] = None
    error: Optional[str] = None


# =============================================================================
# État des jobs (en mémoire)
# =============================================================================

jobs: dict[str, JobInfo] = {}
running_tasks: set[asyncio.Task] = set()  # Garde les références pour éviter le GC


# =============================================================================
# Application FastAPI
# =============================================================================

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle hooks pour l'application."""
    # Startup
    if TEST_MODE:
        log_to_stderr("=" * 60 + "\n")
        log_to_stderr("🧪 TEST MODE ENABLED - Claude will NOT be called\n")
        log_to_stderr("   Will send 1+1=2 and test JSON report instead\n")
        log_to_stderr("=" * 60 + "\n")
    log_to_stderr("🧹 Cleaning expired worktrees on startup...\n")
    cleaned = await async_cleanup_expired()
    log_to_stderr(f"✅ Startup complete ({cleaned} worktrees cleaned)\n")
    yield
    # Shutdown: rien de spécial pour l'instant
    log_to_stderr("👋 Shutting down...\n")


app = FastAPI(
    title="Claude Analysis API",
    description="API pour déclencher des analyses de code avec Claude",
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# WebSocket Error Notification
# =============================================================================


async def run_test_analysis(request: ClaudeRequest) -> None:
    """
    Mode test: envoie 1+1=2 puis un fichier JSON de test via WebSocket.
    Utilisé pour tester le protocole WebSocket sans lancer Claude.
    """
    job_id = request.jobId
    ws_url = f"{WS_BASE_URL}/api/ws/jobs/{job_id}"

    log_to_stderr(f"[TEST MODE] Starting test analysis for job {job_id}\n")

    # Marquer comme en cours
    if job_id in jobs:
        jobs[job_id].status = JobStatus.RUNNING

    try:
        # Connexion WebSocket
        async with asyncio.timeout(30):
            websocket = await websockets.connect(ws_url)

        # Attendre le message "connected"
        async with asyncio.timeout(10):
            connected_msg = await websocket.recv()
            connected_data = json.loads(connected_msg)
            if connected_data.get("type") == "connected":
                log_to_stderr(f"[TEST MODE] WebSocket connected\n")

        async with websocket:
            notifier = WebSocketNotifier(websocket)

            # Démarrer l'action
            await notifier.action_started()
            await notifier.step_started("setup")

            # Test 1: 1+1=2
            await notifier.step_log("Calculating 1+1...")
            await asyncio.sleep(0.5)  # Petit délai pour voir les logs
            result = 1 + 1
            await notifier.step_log(f"1 + 1 = {result}")
            log_to_stderr(f"[TEST MODE] 1 + 1 = {result}\n")
            
            await notifier.step_complete("success", f"## Setup\n\n1 + 1 = {result}")

            # Test 2: Créer et envoyer un fichier JSON de test
            await notifier.step_started("report")
            await notifier.step_log("Creating test JSON report...")

            # Créer le fichier JSON de test
            test_report = {
                "test": True,
                "result": "1+1=2",
                "timestamp": datetime.now().isoformat(),
                "job_id": job_id,
                "issues": [
                    {
                        "id": "TEST-001",
                        "severity": "info",
                        "message": "This is a test issue",
                        "file": "test.py",
                        "line": 42
                    },
                    {
                        "id": "TEST-002",
                        "severity": "warning",
                        "message": "Another test issue with more details",
                        "file": "another.py",
                        "line": 100
                    }
                ],
                "summary": {
                    "total_issues": 2,
                    "by_severity": {"info": 1, "warning": 1}
                }
            }

            # Créer le dossier reports si nécessaire
            reports_dir = Path("reports")
            reports_dir.mkdir(exist_ok=True)

            # Écrire le fichier
            report_path = reports_dir / f"test-report-{job_id}.json"
            with open(report_path, "w") as f:
                json.dump(test_report, f, indent=2, ensure_ascii=False)

            log_to_stderr(f"[TEST MODE] Created test report: {report_path}\n")
            await notifier.step_log(f"Created: {report_path}")

            # Envoyer l'artifact
            await notifier.step_log(f"Sending artifact: {report_path}")
            artifact_sent = await notifier.send_artifact(str(report_path), "report")

            if artifact_sent:
                await notifier.step_log("Artifact sent successfully!")
                await notifier.step_complete("success", f"## Report\n\nArtifact sent: {report_path}")
            else:
                await notifier.step_log("Failed to send artifact", "stderr")
                await notifier.step_complete("failure", f"## Report\n\nFailed to send artifact")

            await notifier.action_complete()

            # Marquer le job comme terminé
            if job_id in jobs:
                jobs[job_id].status = JobStatus.COMPLETED
                jobs[job_id].completed_at = datetime.now()
                jobs[job_id].result = {"test": True, "success": artifact_sent}

            log_to_stderr(f"[TEST MODE] Test completed for job {job_id}\n")

    except Exception as e:
        error_msg = str(e)
        log_to_stderr(f"[TEST MODE] Error: {error_msg}\n")

        if job_id in jobs:
            jobs[job_id].status = JobStatus.FAILED
            jobs[job_id].error = error_msg
            jobs[job_id].completed_at = datetime.now()


async def send_error_to_websocket(job_id: str, error_msg: str) -> None:
    """
    Envoie une erreur via WebSocket au client.
    Utilisé quand une erreur survient avant que launch_claude_stream_json soit appelé.
    """
    ws_url = f"{WS_BASE_URL}/api/ws/jobs"
    try:
        async with asyncio.timeout(30):
            ws = await websockets.connect(f"{ws_url}/{job_id}")

        # Attendre le message "connected"
        async with asyncio.timeout(10):
            connected_msg = await ws.recv()
            connected_data = json.loads(connected_msg)
            if connected_data.get("type") == "connected":
                log_to_stderr(f"[WS Error] Connected for error notification\n")

        async with ws:
            notifier = WebSocketNotifier(ws)
            await notifier.action_started()
            await notifier.fail_with_error(error_msg)
            log_to_stderr(f"[WS Error] Error sent to client: {error_msg}\n")

    except Exception as e:
        log_to_stderr(f"[WS Error] Failed to send error via WebSocket: {e}\n")


async def send_no_files_to_websocket(job_id: str, git_context: GitContext) -> None:
    """
    Notifie le WebSocket qu'il n'y a pas de fichiers à analyser.
    Envoie un action_complete avec succès mais sans rapport.
    """
    ws_url = f"{WS_BASE_URL}/api/ws/jobs"
    try:
        async with asyncio.timeout(30):
            ws = await websockets.connect(f"{ws_url}/{job_id}")

        # Attendre le message "connected"
        async with asyncio.timeout(10):
            connected_msg = await ws.recv()
            connected_data = json.loads(connected_msg)
            if connected_data.get("type") == "connected":
                log_to_stderr(f"[WS NoFiles] Connected for notification\n")

        async with ws:
            notifier = WebSocketNotifier(ws)
            await notifier.action_started()
            await notifier.step_started("setup")
            await notifier.step_log(f"Git context: {git_context.from_commit_short}..{git_context.to_commit_short}")
            await notifier.step_log(f"Parent branch: {git_context.parent_branch}")
            await notifier.step_log("No code files to analyze in this commit range")
            await notifier.step_complete("success", f"## Setup\n\nNo code files to analyze\n\n- From: {git_context.from_commit_short}\n- To: {git_context.to_commit_short}")
            await notifier.action_complete()
            log_to_stderr(f"[WS NoFiles] Notification sent to client\n")

    except Exception as e:
        log_to_stderr(f"[WS NoFiles] Failed to send notification via WebSocket: {e}\n")


# =============================================================================
# Tâches en arrière-plan
# =============================================================================

async def run_claude_analysis(request: ClaudeRequest) -> None:
    """
    Exécute l'analyse Claude en arrière-plan (async).
    Met à jour le statut du job au fur et à mesure.

    Workflow:
    1. Créer un worktree isolé pour le commit
    2. Résoudre le contexte git (diff, fichiers modifiés)
    3. Lancer Claude dans le worktree
    """
    job_id = request.jobId
    worktree_mgr = WorktreeManager()
    working_dir = None

    # Marquer comme en cours
    if job_id in jobs:
        jobs[job_id].status = JobStatus.RUNNING

    try:
        log_to_stderr(f"[Job {job_id}] Starting Claude analysis...\n")

        # === ÉTAPE 1: Créer le worktree isolé ===
        try:
            working_dir = worktree_mgr.create_worktree(request.commitSha, request.branchName)
            log_to_stderr(f"[Job {job_id}] Worktree ready: {working_dir}\n")
        except RuntimeError as e:
            raise RuntimeError(f"Worktree creation failed: {e}")

        # === ÉTAPE 2: Résoudre le contexte git ===
        # Note: on utilise le repo principal pour le contexte git
        # car le worktree est en détached HEAD
        try:
            git_context = resolve_git_context(
                git_param=request.lastAnalyzedCommit,
                commit_sha=request.commitSha,
                branch_name=request.branchName
            )
        except ValueError as e:
            raise ValueError(f"Git context resolution failed: {e}")

        log_to_stderr(f"[Job {job_id}] Git context resolved:\n")
        log_to_stderr(f"  Mode: {git_context.detection_mode}\n")
        log_to_stderr(f"  Parent branch: {git_context.parent_branch}\n")
        log_to_stderr(f"  From: {git_context.from_commit_short}\n")
        log_to_stderr(f"  To: {git_context.to_commit_short}\n")
        log_to_stderr(f"  Files: {len(git_context.files_changed)} files\n")

        # === ÉTAPE 2.5: Fetch SonarCloud issues (si configuré) ===
        # Sauvegarder dans .claude/sonar/issues.json (emplacement attendu par /analyze)
        sonar_dir = Path(".claude/sonar")
        sonar_dir.mkdir(parents=True, exist_ok=True)
        sonar_issues_path = sonar_dir / "issues.json"

        sonar_data = await fetch_sonar_issues(
            git_context=git_context,
            output_path=sonar_issues_path,
            branch_name=request.branchName,
        )

        if sonar_data:
            log_to_stderr(f"[Job {job_id}] SonarCloud issues saved to {sonar_issues_path}\n")
            log_to_stderr(f"[Job {job_id}] /analyze will transform via transform-sonar.py\n")

        # Vérifier s'il y a des fichiers à analyser
        if not git_context.files_changed:
            log_to_stderr(f"[Job {job_id}] No code files to analyze\n")

            # Notifier le WebSocket que l'analyse est terminée (rien à faire)
            await send_no_files_to_websocket(job_id, git_context)

            if job_id in jobs:
                jobs[job_id].status = JobStatus.COMPLETED
                jobs[job_id].completed_at = datetime.now()
                jobs[job_id].result = {
                    "success": True,
                    "message": "No code files to analyze",
                    "files_count": 0
                }
            return

        # === ÉTAPE 3: Construire le prompt et lancer Claude ===
        prompt = build_analysis_prompt(git_context, request)

        # Lancer l'analyse async dans le worktree isolé
        result = await launch_claude_stream_json(
            prompt=prompt,
            request=request,
            working_dir=working_dir,
            max_timeout=7200,
            verbosity=1
        )

        # Mettre à jour avec le résultat
        if job_id in jobs:
            jobs[job_id].completed_at = datetime.now()
            if result and result.get("success"):
                jobs[job_id].status = JobStatus.COMPLETED
                jobs[job_id].result = result
            else:
                jobs[job_id].status = JobStatus.FAILED
                jobs[job_id].error = result.get("error") if result else "Unknown error"

        log_to_stderr(f"[Job {job_id}] Analysis completed.\n")

    except Exception as e:
        error_msg = str(e)
        log_to_stderr(f"[Job {job_id}] Error: {error_msg}\n")

        # Envoyer l'erreur via WebSocket (pour les erreurs qui surviennent avant launch_claude_stream_json)
        await send_error_to_websocket(job_id, error_msg)

        if job_id in jobs:
            jobs[job_id].status = JobStatus.FAILED
            jobs[job_id].error = error_msg
            jobs[job_id].completed_at = datetime.now()


# =============================================================================
# Routes
# =============================================================================

@app.get("/")
def read_root():
    """Health check."""
    return {"status": "ok", "service": "Claude Analysis API"}


@app.post("/trigger")
async def launch_claude(request: ClaudeRequest):
    """
    Déclenche une analyse Claude en arrière-plan.

    Returns:
        Informations sur le job créé
    """
    # Vérifier l'action AVANT de créer le job
    if not TEST_MODE and request.action != 'issue_detector':
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported action: {request.action}. Only 'issue_detector' is supported."
        )

    # Vérifier si le job existe déjà
    if request.jobId in jobs:
        existing = jobs[request.jobId]
        if existing.status in [JobStatus.PENDING, JobStatus.RUNNING]:
            raise HTTPException(
                status_code=409,
                detail=f"Job {request.jobId} is already {existing.status.value}"
            )

    # Note: Le worktree est créé dans run_claude_analysis()
    # Plus besoin de switch_branch() - chaque job a son worktree isolé

    # Logger les infos
    log_to_stderr(f"Lancement de Claude pour la branche: {request.branchName}\n")
    log_to_stderr(f"Commit: {request.commitSha}\n")
    log_to_stderr(f"Job ID: {request.jobId}\n")
    log_to_stderr(f"Action: {request.action}\n")
    log_to_stderr("=" * 60 + "\n\n")

    # Créer l'entrée du job
    jobs[request.jobId] = JobInfo(
        jobId=request.jobId,
        status=JobStatus.PENDING,
        started_at=datetime.now()
    )

    # Lancer en arrière-plan avec asyncio (non-bloquant)
    if TEST_MODE:
        # Mode test: envoie 1+1=2 puis un JSON de test
        log_to_stderr("[TEST MODE] Using test analysis instead of Claude\n")
        task = asyncio.create_task(run_test_analysis(request))
        running_tasks.add(task)
        task.add_done_callback(running_tasks.discard)
    else:
        # Action 'issue_detector' (déjà validée au début de la fonction)
        task = asyncio.create_task(run_claude_analysis(request))
        running_tasks.add(task)
        task.add_done_callback(running_tasks.discard)  # Nettoie quand terminé

    return {
        "jobId": request.jobId,
        "status": "accepted",
        "message": "Job accepted and queued for processing"
    }


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """
    Récupère le statut d'un job.

    Args:
        job_id: L'identifiant du job

    Returns:
        Informations sur le job
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = jobs[job_id]
    return {
        "jobId": job.jobId,
        "status": job.status.value,
        "started_at": job.started_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error
    }


@app.get("/jobs")
def list_jobs():
    """
    Liste tous les jobs.

    Returns:
        Liste des jobs avec leur statut
    """
    return {
        "jobs": [
            {
                "jobId": job.jobId,
                "status": job.status.value,
                "started_at": job.started_at.isoformat()
            }
            for job in jobs.values()
        ],
        "total": len(jobs)
    }


# =============================================================================
# Routes Admin (Worktrees)
# =============================================================================

@app.get("/admin/worktrees")
def list_worktrees():
    """
    Liste tous les worktrees actifs.

    Returns:
        Liste des worktrees avec leur état
    """
    mgr = WorktreeManager()
    worktrees = mgr.list_worktrees()
    return {
        "worktrees": worktrees,
        "total": len(worktrees),
        "base_path": str(mgr.base_path),
        "ttl_hours": mgr.ttl / 3600
    }


@app.post("/admin/worktrees/cleanup")
async def cleanup_worktrees():
    """
    Force le nettoyage des worktrees expirés.

    Returns:
        Nombre de worktrees nettoyés
    """
    cleaned = await async_cleanup_expired()
    return {
        "cleaned": cleaned,
        "message": f"{cleaned} worktree(s) cleaned"
    }


@app.delete("/admin/worktrees/{commit_sha}")
def delete_worktree(commit_sha: str):
    """
    Supprime un worktree spécifique.

    Args:
        commit_sha: Le SHA du commit (12 premiers caractères suffisent)

    Returns:
        Statut de la suppression
    """
    mgr = WorktreeManager()
    success = mgr.cleanup_worktree(commit_sha)

    if success:
        return {"status": "deleted", "commit": commit_sha}
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete worktree for {commit_sha}"
        )


# =============================================================================
# Routes Admin (Validation)
# =============================================================================

class ValidateRequest(BaseModel):
    """Requête de validation d'un rapport."""
    report_path: str
    strict: bool = False


@app.post("/admin/validate")
def validate_report_api(request: ValidateRequest):
    """
    Valide la qualité d'un rapport d'issues.

    Args:
        request: Chemin du rapport et options

    Returns:
        Résultats de validation
    """
    if not VALIDATOR_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Validator module not available"
        )

    report_path = Path(request.report_path)

    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Report not found: {request.report_path}"
        )

    result = validate_report(report_path, strict=request.strict)

    if result is None:
        raise HTTPException(
            status_code=500,
            detail="Validation failed"
        )

    return result
