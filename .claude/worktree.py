# worktree.py
"""
Gestionnaire de git worktrees pour isoler les analyses par commit.
Permet à plusieurs instances Claude de travailler en parallèle sur différents commits.
"""

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import filelock
except ImportError:
    filelock = None  # Fallback sans lock

# Import du gestionnaire AgentDB
try:
    from agentdb_manager import AgentDBManager, get_agentdb_manager
except ImportError:
    AgentDBManager = None
    get_agentdb_manager = None


def log_to_stderr(text: str) -> None:
    """Log vers stderr pour voir en temps réel dans le terminal."""
    sys.stderr.write(text)
    sys.stderr.flush()


# =============================================================================
# Configuration
# =============================================================================

WORKTREE_BASE = Path(os.environ.get("CRE_WORKTREE_DIR", "/tmp/cre-worktrees"))
WORKTREE_TTL = int(os.environ.get("CRE_WORKTREE_TTL", 3600 * 24))  # 24h par défaut
MAIN_REPO = Path(__file__).parent.parent  # /home/.../flow


def get_git_command(args: list[str]) -> list[str]:
    """
    Construit la commande git avec sshpass si GIT_SSH_PASSWORD est défini.

    Args:
        args: Liste des arguments git (sans 'git')

    Returns:
        Liste de commande complète (avec ou sans sshpass)
    """
    git_password = os.environ.get("GIT_SSH_PASSWORD")
    if git_password:
        # Utiliser sshpass pour les commandes qui nécessitent une authentification
        return ["sshpass", "-p", git_password, "git"] + args
    return ["git"] + args


# =============================================================================
# WorktreeManager
# =============================================================================

class WorktreeManager:
    """
    Gère les git worktrees pour isoler les analyses par commit.

    Fonctionnalités:
    - Création de worktree par commit SHA
    - Symlinks vers .claude/ du repo principal (config partagée)
    - Répertoires isolés par job (logs, reports)
    - Cleanup avec TTL
    - Lock pour éviter les créations concurrentes
    """

    # Répertoires .claude/ partagés via symlink (config commune, read-only)
    # Note: agentdb est géré séparément par AgentDBManager (index caché + shared symlink)
    SYMLINK_DIRS = ["config", "agents", "commands", "scripts", "mcp", "sonar"]

    # Répertoires .claude/ COPIÉS (si besoin d'isolation totale)
    COPY_DIRS = []

    # agentdb est géré par AgentDBManager (voir agentdb_manager.py)
    # - shared.sqlite = symlink (checkpoints, historique)
    # - index.sqlite = cache par commit (index du code)

    # Répertoires .claude/ locaux isolés par worktree (créés vides)
    LOCAL_DIRS = ["logs"]

    # Répertoires à la RACINE du worktree (symlink vers repo principal)
    ROOT_SYMLINK_DIRS = ["reports"]

    def __init__(
        self,
        base_path: Path = WORKTREE_BASE,
        main_repo: Path = MAIN_REPO,
        ttl: int = WORKTREE_TTL
    ):
        self.base_path = base_path
        self.main_repo = main_repo
        self.ttl = ttl
        self.base_path.mkdir(parents=True, exist_ok=True)

    def get_worktree_path(self, commit_sha: str) -> Path:
        """Retourne le chemin du worktree pour un commit."""
        return self.base_path / commit_sha[:12]

    def _get_lock(self, commit_sha: str) -> Optional["filelock.FileLock"]:
        """Retourne un lock pour le worktree (ou None si filelock non disponible)."""
        if filelock is None:
            return None
        lock_path = self.base_path / f"{commit_sha[:12]}.lock"
        return filelock.FileLock(lock_path, timeout=60)

    def create_worktree(self, commit_sha: str, branch_name: str) -> Path:
        """
        Crée un worktree pour le commit donné.

        Args:
            commit_sha: Le SHA complet ou partiel du commit
            branch_name: Nom de la branche (pour le cache AgentDB)

        Returns:
            Path vers le worktree créé

        Raises:
            RuntimeError: Si la création échoue
        """
        wt_path = self.get_worktree_path(commit_sha)
        lock = self._get_lock(commit_sha)

        def _create():
            if wt_path.exists():
                # Toujours nettoyer et recréer pour avoir un état propre
                log_to_stderr(f"[Worktree] Nettoyage du worktree existant: {wt_path}\n")
                self._force_remove_worktree(commit_sha)

            log_to_stderr(f"[Worktree] Création pour {commit_sha[:12]}...\n")

            # Vérifier si le commit existe localement
            check_result = subprocess.run(
                ["git", "cat-file", "-t", commit_sha],
                cwd=self.main_repo,
                capture_output=True,
                text=True
            )

            if check_result.returncode != 0:
                # Commit non trouvé localement, tenter un fetch
                log_to_stderr(f"[Worktree] Commit {commit_sha[:12]} non trouvé localement, fetch en cours...\n")
                fetch_result = subprocess.run(
                    get_git_command(["fetch", "--all"]),
                    cwd=self.main_repo,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if fetch_result.returncode != 0:
                    log_to_stderr(f"[Worktree] Warning: git fetch failed: {fetch_result.stderr}\n")

                # Re-vérifier après fetch
                check_result = subprocess.run(
                    ["git", "cat-file", "-t", commit_sha],
                    cwd=self.main_repo,
                    capture_output=True,
                    text=True
                )
                if check_result.returncode != 0:
                    raise RuntimeError(f"Commit {commit_sha} introuvable (même après fetch)")

            # Créer le worktree
            result = subprocess.run(
                ["git", "worktree", "add", "--detach", str(wt_path), commit_sha],
                cwd=self.main_repo,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise RuntimeError(f"Échec création worktree: {result.stderr}")

            # Configurer .claude/ avec AgentDB
            agentdb_info = self._setup_claude_directory(wt_path, commit_sha, branch_name)

            log_to_stderr(f"[Worktree] Créé: {wt_path}\n")
            # agentdb_info peut être un IndexResult ou un dict (fallback)
            if isinstance(agentdb_info, dict):
                needs_indexing = agentdb_info.get("needs_indexing", False)
            else:
                needs_indexing = getattr(agentdb_info, "needs_indexing", False)
            if needs_indexing:
                log_to_stderr(f"[Worktree] AgentDB needs indexing for this branch\n")

            return wt_path

        # Exécuter avec ou sans lock
        if lock:
            with lock:
                return _create()
        else:
            return _create()

    def _setup_claude_directory(self, wt_path: Path, commit_sha: str, branch_name: str) -> dict:
        """
        Configure le répertoire .claude avec symlinks vers le repo principal.

        Structure:
        - Symlinks pour config partagée (agents, commands, etc.)
        - AgentDB avec cache d'index par branche
        - Répertoires locaux pour isolation (logs)

        Args:
            wt_path: Chemin du worktree
            commit_sha: SHA du commit (pour le cache AgentDB)
            branch_name: Nom de la branche (pour le cache AgentDB)

        Returns:
            dict avec infos AgentDB (needs_indexing, paths, etc.)
        """
        claude_dir = wt_path / ".claude"
        main_claude = self.main_repo / ".claude"
        agentdb_info = {}

        # Supprimer .claude existant (copié par git worktree si présent)
        if claude_dir.exists():
            shutil.rmtree(claude_dir)
        claude_dir.mkdir()

        # Copier settings.json (fichier, pas répertoire)
        settings_src = main_claude / "settings.json"
        if settings_src.exists():
            shutil.copy2(settings_src, claude_dir / "settings.json")

        # Créer symlinks vers le repo principal (read-only)
        for dir_name in self.SYMLINK_DIRS:
            src = main_claude / dir_name
            dst = claude_dir / dir_name
            if src.exists():
                dst.symlink_to(src)
                log_to_stderr(f"  [Symlink] {dir_name} -> {src}\n")

        # Copier les répertoires modifiables (si configurés)
        for dir_name in self.COPY_DIRS:
            src = main_claude / dir_name
            dst = claude_dir / dir_name
            if src.exists():
                shutil.copytree(src, dst)
                log_to_stderr(f"  [Copy] {dir_name}/ (isolated)\n")

        # Créer répertoires locaux isolés
        for dir_name in self.LOCAL_DIRS:
            local_dir = claude_dir / dir_name
            local_dir.mkdir()
            log_to_stderr(f"  [Local] {dir_name}/\n")

        # Configurer AgentDB avec le manager (cache d'index par branche + shared symlink)
        if AgentDBManager is not None:
            agentdb_mgr = get_agentdb_manager()
            agentdb_info = agentdb_mgr.setup_for_worktree(
                worktree_path=wt_path,
                main_repo=self.main_repo,
                commit_sha=commit_sha,
                branch_name=branch_name
            )
        else:
            # Fallback: symlink simple si AgentDBManager non disponible
            agentdb_src = main_claude / "agentdb"
            agentdb_dst = claude_dir / "agentdb"
            if agentdb_src.exists():
                agentdb_dst.symlink_to(agentdb_src)
                log_to_stderr(f"  [Symlink] agentdb -> {agentdb_src} (fallback)\n")
            agentdb_info = {"needs_indexing": False}

        # Créer symlinks à la RACINE du worktree (ex: reports/)
        for dir_name in self.ROOT_SYMLINK_DIRS:
            src = self.main_repo / dir_name
            dst = wt_path / dir_name
            # Supprimer si existe (git worktree peut avoir copié le dossier)
            if dst.exists() and not dst.is_symlink():
                shutil.rmtree(dst)
            if dst.is_symlink():
                dst.unlink()
            if src.exists():
                dst.symlink_to(src)
                log_to_stderr(f"  [Root Symlink] {dir_name}/ -> {src}\n")

        return agentdb_info

    def validate_worktree(self, commit_sha: str) -> bool:
        """
        Vérifie que le worktree est valide et au bon commit.

        Args:
            commit_sha: Le SHA attendu

        Returns:
            True si valide, False sinon
        """
        wt_path = self.get_worktree_path(commit_sha)

        if not wt_path.exists():
            return False

        # Vérifier que c'est un repo git valide
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=wt_path,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return False

        # Vérifier que le HEAD correspond au commit attendu
        head_sha = result.stdout.strip()
        return head_sha.startswith(commit_sha[:12]) or commit_sha.startswith(head_sha[:12])

    def _force_remove_worktree(self, commit_sha: str) -> None:
        """Supprime un worktree de force (même corrompu)."""
        wt_path = self.get_worktree_path(commit_sha)

        # Essayer git worktree remove
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt_path)],
            cwd=self.main_repo,
            capture_output=True
        )

        # Si le répertoire existe encore, le supprimer manuellement
        if wt_path.exists():
            shutil.rmtree(wt_path)

        # Nettoyer les références git
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=self.main_repo,
            capture_output=True
        )

    def cleanup_worktree(self, commit_sha: str) -> bool:
        """
        Supprime un worktree proprement.

        Args:
            commit_sha: Le SHA du commit

        Returns:
            True si supprimé, False si erreur
        """
        wt_path = self.get_worktree_path(commit_sha)

        if not wt_path.exists():
            return True

        log_to_stderr(f"[Worktree] Cleanup: {wt_path}\n")

        try:
            self._force_remove_worktree(commit_sha)
            return True
        except Exception as e:
            log_to_stderr(f"[Worktree] Erreur cleanup: {e}\n")
            return False

    def cleanup_expired_worktrees(self) -> int:
        """
        Supprime les worktrees expirés (plus vieux que TTL).

        Returns:
            Nombre de worktrees supprimés
        """
        if not self.base_path.exists():
            return 0

        now = time.time()
        cleaned = 0

        for entry in self.base_path.iterdir():
            # Ignorer les fichiers .lock
            if entry.suffix == ".lock":
                continue

            if not entry.is_dir():
                continue

            try:
                mtime = entry.stat().st_mtime
                age = now - mtime

                if age > self.ttl:
                    commit_sha = entry.name
                    log_to_stderr(f"[Worktree] Expiré ({age/3600:.1f}h): {entry}\n")
                    if self.cleanup_worktree(commit_sha):
                        cleaned += 1
                        # Supprimer aussi le fichier .lock
                        lock_file = self.base_path / f"{commit_sha}.lock"
                        if lock_file.exists():
                            lock_file.unlink()
            except Exception as e:
                log_to_stderr(f"[Worktree] Erreur inspection {entry}: {e}\n")

        # Nettoyer les fichiers .lock orphelins (sans répertoire correspondant)
        orphan_locks = 0
        for entry in self.base_path.iterdir():
            if entry.suffix != ".lock":
                continue
            # Vérifier si le répertoire correspondant existe
            worktree_name = entry.stem  # "abc123.lock" -> "abc123"
            worktree_dir = self.base_path / worktree_name
            if not worktree_dir.exists():
                try:
                    entry.unlink()
                    orphan_locks += 1
                    log_to_stderr(f"[Worktree] Lock orphelin supprimé: {entry.name}\n")
                except Exception as e:
                    log_to_stderr(f"[Worktree] Erreur suppression lock {entry}: {e}\n")

        if orphan_locks > 0:
            log_to_stderr(f"[Worktree] {orphan_locks} lock(s) orphelin(s) nettoyé(s)\n")

        if cleaned > 0:
            log_to_stderr(f"[Worktree] {cleaned} worktree(s) nettoyé(s)\n")

        return cleaned

    def list_worktrees(self) -> list[dict]:
        """
        Liste tous les worktrees gérés.

        Returns:
            Liste de dicts avec path, commit, age, valid
        """
        if not self.base_path.exists():
            return []

        worktrees = []
        now = time.time()

        for entry in self.base_path.iterdir():
            if entry.suffix == ".lock" or not entry.is_dir():
                continue

            try:
                mtime = entry.stat().st_mtime
                commit_sha = entry.name
                worktrees.append({
                    "path": str(entry),
                    "commit": commit_sha,
                    "age_hours": (now - mtime) / 3600,
                    "valid": self.validate_worktree(commit_sha)
                })
            except Exception:
                pass

        return worktrees


# =============================================================================
# Fonctions utilitaires
# =============================================================================

def get_worktree_manager() -> WorktreeManager:
    """Factory pour obtenir une instance de WorktreeManager."""
    return WorktreeManager()


async def async_cleanup_expired() -> int:
    """Version async du cleanup pour appel depuis FastAPI."""
    loop = asyncio.get_event_loop()
    manager = get_worktree_manager()
    return await loop.run_in_executor(None, manager.cleanup_expired_worktrees)
