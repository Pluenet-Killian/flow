# main.py
"""
API FastAPI pour déclencher les analyses Claude.
"""

import asyncio
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime
from enum import Enum

from claude import switch_branch, launch_claude_stream_json, log_to_stderr


# =============================================================================
# Git Utilities
# =============================================================================

# Extensions de code à analyser
CODE_EXTENSIONS = ['.c', '.cpp', '.h', '.hpp', '.py', '.js', '.ts', '.tsx', '.go', '.rs', '.java']


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


def run_git_command(args: list[str], timeout: int = 60) -> tuple[bool, str]:
    """
    Exécute une commande git et retourne (success, output).

    Args:
        args: Liste des arguments git (sans 'git')
        timeout: Timeout en secondes

    Returns:
        Tuple (success: bool, output: str)
    """
    try:
        result = subprocess.run(
            ['git'] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
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


def resolve_git_context(git_param: str, commit_sha: str, branch_name: str) -> GitContext:
    """
    Résout le contexte git selon le paramètre 'git'.

    Args:
        git_param: "0" pour auto-détection, ou hash de commit
        commit_sha: Le commit cible (to_commit)
        branch_name: La branche actuelle

    Returns:
        GitContext avec toutes les informations nécessaires
    """
    if git_param == "0":
        # Mode 1: Auto-détection de la branche parente
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
    prompt_path = Path(".claude/commands/analyze_py.md")
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
    git: str  # "0" pour auto-détection branche parente, ou hash de commit


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

app = FastAPI(
    title="Claude Analysis API",
    description="API pour déclencher des analyses de code avec Claude",
    version="1.0.0",
    
)


# =============================================================================
# Tâches en arrière-plan
# =============================================================================

async def run_claude_analysis(request: ClaudeRequest) -> None:
    """
    Exécute l'analyse Claude en arrière-plan (async).
    Met à jour le statut du job au fur et à mesure.
    """
    job_id = request.jobId

    # Marquer comme en cours
    if job_id in jobs:
        jobs[job_id].status = JobStatus.RUNNING

    try:
        log_to_stderr(f"[Job {job_id}] Starting Claude analysis...\n")

        # Résoudre le contexte git
        try:
            git_context = resolve_git_context(
                git_param=request.git,
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

        # Vérifier s'il y a des fichiers à analyser
        if not git_context.files_changed:
            log_to_stderr(f"[Job {job_id}] No code files to analyze\n")
            if job_id in jobs:
                jobs[job_id].status = JobStatus.COMPLETED
                jobs[job_id].completed_at = datetime.now()
                jobs[job_id].result = {
                    "success": True,
                    "message": "No code files to analyze",
                    "files_count": 0
                }
            return

        # Construire le prompt avec le contexte git
        prompt = build_analysis_prompt(git_context, request)

        # Lancer l'analyse async (ne bloque plus le serveur)
        result = await launch_claude_stream_json(
            prompt=prompt,
            request=request,
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
        log_to_stderr(f"[Job {job_id}] Error: {e}\n")
        if job_id in jobs:
            jobs[job_id].status = JobStatus.FAILED
            jobs[job_id].error = str(e)
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
    # Vérifier si le job existe déjà
    if request.jobId in jobs:
        existing = jobs[request.jobId]
        if existing.status in [JobStatus.PENDING, JobStatus.RUNNING]:
            raise HTTPException(
                status_code=409,
                detail=f"Job {request.jobId} is already {existing.status.value}"
            )

    # Changer de branche
    if not switch_branch(request.branchName):
        raise HTTPException(
            status_code=400,
            detail=f"Failed to switch to branch: {request.branchName}"
        )

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
    if request.action == 'issue_detector':
        task = asyncio.create_task(run_claude_analysis(request))
        running_tasks.add(task)
        task.add_done_callback(running_tasks.discard)  # Nettoie quand terminé
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported action: {request.action}"
        )

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
