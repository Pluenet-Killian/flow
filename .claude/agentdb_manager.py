# agentdb_manager.py
"""
Gestionnaire d'AgentDB pour les worktrees - Architecture Hybride.

Structure du cache:
    /tmp/cre-agentdb-cache/
    ├── branches/
    │   ├── main/
    │   │   ├── current.sqlite      ← Index courant
    │   │   ├── checkpoint.json     ← {"commit": "...", "timestamp": ...}
    │   │   └── snapshots/
    │   │       └── abc123.sqlite   ← Snapshots historiques
    │   └── feature-auth/
    │       └── ...

Stratégie:
- shared.sqlite : Symlink vers repo principal (checkpoints, historique)
- index.sqlite  : Cache par branche avec incrémentalité
- Snapshots     : Pour retour arrière ou branches divergentes
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


def log_to_stderr(text: str) -> None:
    """Log vers stderr."""
    sys.stderr.write(text)
    sys.stderr.flush()


# =============================================================================
# Configuration
# =============================================================================

AGENTDB_CACHE_DIR = Path(os.environ.get("CRE_AGENTDB_CACHE", "/tmp/cre-agentdb-cache"))
AGENTDB_MAX_SNAPSHOTS_PER_BRANCH = int(os.environ.get("CRE_AGENTDB_MAX_SNAPSHOTS", 5))
AGENTDB_SNAPSHOT_TTL = int(os.environ.get("CRE_AGENTDB_SNAPSHOT_TTL", 14 * 24 * 3600))  # 14 jours

# Fichiers AgentDB à symlinker (code, read-only)
AGENTDB_SYMLINK_FILES = [
    "__init__.py", "config.py", "crud.py", "db.py",
    "indexer.py", "models.py", "queries.py", "query.sh", "schema.sql",
]
AGENTDB_SYMLINK_DIRS = ["__pycache__"]

# Fichiers de données
AGENTDB_SHARED_DB = "shared.sqlite"
AGENTDB_INDEX_DB = "index.sqlite"
AGENTDB_LEGACY_DB = "db.sqlite"


# =============================================================================
# Git Utilities
# =============================================================================

def run_git(args: list[str], cwd: Path = None) -> tuple[bool, str]:
    """Exécute une commande git."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def is_ancestor(commit: str, descendant: str, cwd: Path = None) -> bool:
    """Vérifie si commit est un ancêtre de descendant."""
    success, _ = run_git(["merge-base", "--is-ancestor", commit, descendant], cwd)
    return success


def is_descendant(commit: str, ancestor: str, cwd: Path = None) -> bool:
    """Vérifie si commit descend de ancestor."""
    return is_ancestor(ancestor, commit, cwd)


def get_merge_base(commit1: str, commit2: str, cwd: Path = None) -> Optional[str]:
    """Retourne le merge-base entre deux commits."""
    success, result = run_git(["merge-base", commit1, commit2], cwd)
    return result if success else None


def get_commit_distance(from_commit: str, to_commit: str, cwd: Path = None) -> int:
    """Compte les commits entre from_commit et to_commit."""
    success, result = run_git(["rev-list", "--count", f"{from_commit}..{to_commit}"], cwd)
    if success:
        try:
            return int(result)
        except ValueError:
            pass
    return -1


def normalize_branch_name(branch: str) -> str:
    """Normalise le nom de branche pour le système de fichiers."""
    return branch.replace("/", "-").replace("\\", "-").replace(" ", "_")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class BranchCheckpoint:
    """État du cache d'une branche."""
    commit: str
    timestamp: float
    indexed_files: int = 0

    def to_dict(self) -> dict:
        return {
            "commit": self.commit,
            "timestamp": self.timestamp,
            "indexed_files": self.indexed_files,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BranchCheckpoint":
        return cls(
            commit=data["commit"],
            timestamp=data["timestamp"],
            indexed_files=data.get("indexed_files", 0),
        )


@dataclass
class IndexResult:
    """Résultat de la configuration d'index."""
    index_path: Path
    shared_path: Path
    needs_indexing: bool
    strategy: str  # "cache_hit", "incremental", "snapshot", "rebuild"
    from_commit: Optional[str] = None  # Pour incrémental


# =============================================================================
# Branch Cache Manager
# =============================================================================

class BranchCache:
    """Gère le cache d'une branche spécifique."""

    def __init__(self, cache_dir: Path, branch_name: str):
        self.branch_name = branch_name
        self.branch_dir = cache_dir / "branches" / normalize_branch_name(branch_name)
        self.current_db = self.branch_dir / "current.sqlite"
        self.checkpoint_file = self.branch_dir / "checkpoint.json"
        self.snapshots_dir = self.branch_dir / "snapshots"

    def exists(self) -> bool:
        """Vérifie si le cache de la branche existe."""
        return self.current_db.exists() and self.checkpoint_file.exists()

    def ensure_dirs(self) -> None:
        """Crée les répertoires nécessaires."""
        self.branch_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(exist_ok=True)

    def get_checkpoint(self) -> Optional[BranchCheckpoint]:
        """Lit le checkpoint de la branche."""
        if not self.checkpoint_file.exists():
            return None
        try:
            data = json.loads(self.checkpoint_file.read_text())
            return BranchCheckpoint.from_dict(data)
        except Exception:
            return None

    def set_checkpoint(self, checkpoint: BranchCheckpoint) -> None:
        """Écrit le checkpoint de la branche."""
        self.ensure_dirs()
        self.checkpoint_file.write_text(json.dumps(checkpoint.to_dict(), indent=2))

    def create_snapshot(self, commit: str) -> Optional[Path]:
        """Crée un snapshot de l'index actuel."""
        if not self.current_db.exists():
            return None

        self.ensure_dirs()
        snapshot_path = self.snapshots_dir / f"{commit[:12]}.sqlite"

        try:
            shutil.copy2(self.current_db, snapshot_path)
            log_to_stderr(f"  [AgentDB] Snapshot créé: {commit[:12]}\n")
            self._cleanup_old_snapshots()
            return snapshot_path
        except Exception as e:
            log_to_stderr(f"  [AgentDB] Erreur snapshot: {e}\n")
            return None

    def find_snapshot(self, commit: str) -> Optional[Path]:
        """Cherche un snapshot exact pour ce commit."""
        snapshot_path = self.snapshots_dir / f"{commit[:12]}.sqlite"
        if snapshot_path.exists():
            return snapshot_path
        return None

    def find_nearest_ancestor_snapshot(self, commit: str, cwd: Path = None) -> Optional[tuple[Path, str]]:
        """
        Trouve le snapshot le plus proche qui est un ancêtre du commit.

        Returns:
            Tuple (path, commit_sha) ou None
        """
        if not self.snapshots_dir.exists():
            return None

        candidates = []
        for snapshot in self.snapshots_dir.glob("*.sqlite"):
            snapshot_commit = snapshot.stem
            # Vérifier si le snapshot est un ancêtre
            if is_ancestor(snapshot_commit, commit, cwd):
                # Calculer la distance
                distance = get_commit_distance(snapshot_commit, commit, cwd)
                if distance >= 0:
                    candidates.append((distance, snapshot, snapshot_commit))

        if candidates:
            # Prendre le plus proche (distance minimale)
            candidates.sort(key=lambda x: x[0])
            _, path, sha = candidates[0]
            return path, sha

        return None

    def _cleanup_old_snapshots(self) -> None:
        """Supprime les snapshots excédentaires ou expirés."""
        if not self.snapshots_dir.exists():
            return

        snapshots = []
        now = time.time()

        for path in self.snapshots_dir.glob("*.sqlite"):
            try:
                mtime = path.stat().st_mtime
                age = now - mtime
                snapshots.append((mtime, age, path))
            except Exception:
                pass

        # Trier par date (plus récent en premier)
        snapshots.sort(key=lambda x: x[0], reverse=True)

        for i, (_, age, path) in enumerate(snapshots):
            # Supprimer si trop vieux ou trop nombreux
            if age > AGENTDB_SNAPSHOT_TTL or i >= AGENTDB_MAX_SNAPSHOTS_PER_BRANCH:
                try:
                    path.unlink()
                    log_to_stderr(f"  [AgentDB] Snapshot supprimé: {path.name}\n")
                except Exception:
                    pass


# =============================================================================
# AgentDB Manager (Hybrid Architecture)
# =============================================================================

class AgentDBManager:
    """
    Gestionnaire d'AgentDB avec architecture hybride par branche + snapshots.

    Stratégies:
    1. CACHE_HIT    : Le checkpoint correspond au commit demandé
    2. INCREMENTAL  : Le commit est un descendant du checkpoint
    3. SNAPSHOT     : Utiliser un snapshot ancêtre
    4. REBUILD      : Reconstruire depuis zéro
    """

    def __init__(self, cache_dir: Path = AGENTDB_CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_branch_cache(self, branch_name: str) -> BranchCache:
        """Retourne le cache pour une branche."""
        return BranchCache(self.cache_dir, branch_name)

    def setup_for_worktree(
        self,
        worktree_path: Path,
        main_repo: Path,
        commit_sha: str,
        branch_name: str
    ) -> IndexResult:
        """
        Configure AgentDB pour un worktree.

        Args:
            worktree_path: Chemin du worktree
            main_repo: Chemin du repo principal
            commit_sha: SHA du commit à analyser
            branch_name: Nom de la branche

        Returns:
            IndexResult avec stratégie et chemins
        """
        wt_agentdb = worktree_path / ".claude" / "agentdb"
        main_agentdb = main_repo / ".claude" / "agentdb"

        # Créer le répertoire
        wt_agentdb.mkdir(parents=True, exist_ok=True)

        # 1. Symlinker les fichiers de code
        self._setup_symlinks(wt_agentdb, main_agentdb)

        # 2. Configurer shared.sqlite (symlink)
        shared_path = self._setup_shared_db(wt_agentdb, main_agentdb)

        # 3. Déterminer la stratégie pour index.sqlite
        index_path = wt_agentdb / AGENTDB_INDEX_DB
        result = self._get_index_strategy(
            branch_name=branch_name,
            commit_sha=commit_sha,
            index_path=index_path,
            main_agentdb=main_agentdb,
            cwd=main_repo
        )

        # 4. Appliquer la stratégie
        self._apply_strategy(result, main_agentdb, branch_name, commit_sha)

        # 5. Créer le symlink de rétrocompatibilité db.sqlite -> index.sqlite
        legacy_path = wt_agentdb / AGENTDB_LEGACY_DB
        if not legacy_path.exists():
            legacy_path.symlink_to(AGENTDB_INDEX_DB)

        return IndexResult(
            index_path=index_path,
            shared_path=shared_path,
            needs_indexing=result.needs_indexing,
            strategy=result.strategy,
            from_commit=result.from_commit
        )

    def _setup_symlinks(self, wt_agentdb: Path, main_agentdb: Path) -> None:
        """Configure les symlinks pour le code AgentDB."""
        for filename in AGENTDB_SYMLINK_FILES:
            src = main_agentdb / filename
            dst = wt_agentdb / filename
            if src.exists() and not dst.exists():
                dst.symlink_to(src)

        for dirname in AGENTDB_SYMLINK_DIRS:
            src = main_agentdb / dirname
            dst = wt_agentdb / dirname
            if src.exists() and not dst.exists():
                dst.symlink_to(src)

    def _setup_shared_db(self, wt_agentdb: Path, main_agentdb: Path) -> Path:
        """Configure shared.sqlite (symlink vers repo principal)."""
        shared_src = main_agentdb / AGENTDB_SHARED_DB
        shared_dst = wt_agentdb / AGENTDB_SHARED_DB

        # Migration si shared.sqlite n'existe pas
        if not shared_src.exists():
            legacy_db = main_agentdb / AGENTDB_LEGACY_DB
            if legacy_db.exists():
                log_to_stderr(f"  [AgentDB] Migration: création shared.sqlite\n")
                self._create_shared_db(legacy_db, shared_src)

        if shared_src.exists() and not shared_dst.exists():
            shared_dst.symlink_to(shared_src)
            log_to_stderr(f"  [AgentDB] shared.sqlite -> symlink\n")

        return shared_dst

    def _get_index_strategy(
        self,
        branch_name: str,
        commit_sha: str,
        index_path: Path,
        main_agentdb: Path,
        cwd: Path
    ) -> IndexResult:
        """
        Détermine la stratégie pour obtenir l'index.

        Returns:
            IndexResult avec stratégie mais index_path non encore copié
        """
        cache = self.get_branch_cache(branch_name)
        checkpoint = cache.get_checkpoint()

        # Cas 1: Pas de cache pour cette branche
        if not cache.exists() or checkpoint is None:
            log_to_stderr(f"  [AgentDB] Branche '{branch_name}': pas de cache\n")
            return IndexResult(
                index_path=index_path,
                shared_path=Path(),  # Sera rempli plus tard
                needs_indexing=True,
                strategy="rebuild"
            )

        # Cas 2: Cache HIT exact
        if commit_sha.startswith(checkpoint.commit) or checkpoint.commit.startswith(commit_sha[:12]):
            log_to_stderr(f"  [AgentDB] Cache HIT: {checkpoint.commit[:12]}\n")
            return IndexResult(
                index_path=index_path,
                shared_path=Path(),
                needs_indexing=False,
                strategy="cache_hit"
            )

        # Cas 3: Le commit est un descendant du checkpoint → incrémental
        if is_descendant(commit_sha, checkpoint.commit, cwd):
            distance = get_commit_distance(checkpoint.commit, commit_sha, cwd)
            log_to_stderr(f"  [AgentDB] Incrémental: {checkpoint.commit[:12]} -> {commit_sha[:12]} ({distance} commits)\n")
            return IndexResult(
                index_path=index_path,
                shared_path=Path(),
                needs_indexing=True,
                strategy="incremental",
                from_commit=checkpoint.commit
            )

        # Cas 4: Le commit est un ancêtre du checkpoint → chercher snapshot
        if is_ancestor(commit_sha, checkpoint.commit, cwd):
            snapshot = cache.find_snapshot(commit_sha)
            if snapshot:
                log_to_stderr(f"  [AgentDB] Snapshot exact: {commit_sha[:12]}\n")
                return IndexResult(
                    index_path=index_path,
                    shared_path=Path(),
                    needs_indexing=False,
                    strategy="snapshot"
                )

            # Chercher un ancêtre proche
            ancestor = cache.find_nearest_ancestor_snapshot(commit_sha, cwd)
            if ancestor:
                snapshot_path, ancestor_commit = ancestor
                log_to_stderr(f"  [AgentDB] Snapshot ancêtre: {ancestor_commit[:12]}\n")
                return IndexResult(
                    index_path=index_path,
                    shared_path=Path(),
                    needs_indexing=True,
                    strategy="incremental",
                    from_commit=ancestor_commit
                )

        # Cas 5: Branches divergentes → rebuild
        merge_base = get_merge_base(commit_sha, checkpoint.commit, cwd)
        if merge_base:
            log_to_stderr(f"  [AgentDB] Divergence, merge-base: {merge_base[:12]}\n")
            # Chercher un snapshot au merge-base
            snapshot = cache.find_snapshot(merge_base)
            if snapshot:
                return IndexResult(
                    index_path=index_path,
                    shared_path=Path(),
                    needs_indexing=True,
                    strategy="incremental",
                    from_commit=merge_base
                )

        # Fallback: rebuild complet
        log_to_stderr(f"  [AgentDB] Rebuild complet nécessaire\n")
        return IndexResult(
            index_path=index_path,
            shared_path=Path(),
            needs_indexing=True,
            strategy="rebuild"
        )

    def _apply_strategy(
        self,
        result: IndexResult,
        main_agentdb: Path,
        branch_name: str,
        commit_sha: str
    ) -> None:
        """Applique la stratégie en copiant les bons fichiers."""
        cache = self.get_branch_cache(branch_name)
        cache.ensure_dirs()

        if result.strategy == "cache_hit":
            # Copier depuis le cache courant
            shutil.copy2(cache.current_db, result.index_path)
            log_to_stderr(f"  [AgentDB] index.sqlite <- cache courant\n")

        elif result.strategy == "incremental":
            # Copier depuis le cache courant (sera mis à jour par bootstrap)
            if cache.current_db.exists():
                shutil.copy2(cache.current_db, result.index_path)
                log_to_stderr(f"  [AgentDB] index.sqlite <- cache (incrémental depuis {result.from_commit[:12]})\n")
            else:
                # Fallback: copier depuis main
                self._copy_from_main(main_agentdb, result.index_path)

        elif result.strategy == "snapshot":
            # Copier depuis le snapshot
            snapshot = cache.find_snapshot(commit_sha)
            if snapshot:
                shutil.copy2(snapshot, result.index_path)
                log_to_stderr(f"  [AgentDB] index.sqlite <- snapshot {commit_sha[:12]}\n")
            else:
                self._copy_from_main(main_agentdb, result.index_path)

        else:  # rebuild
            # Copier depuis main comme base
            self._copy_from_main(main_agentdb, result.index_path)

    def _copy_from_main(self, main_agentdb: Path, target: Path) -> None:
        """Copie l'index depuis le repo principal."""
        # Essayer index.sqlite d'abord, puis db.sqlite
        for name in [AGENTDB_INDEX_DB, AGENTDB_LEGACY_DB]:
            src = main_agentdb / name
            if src.exists():
                shutil.copy2(src, target)
                log_to_stderr(f"  [AgentDB] index.sqlite <- {name} (main)\n")
                return

        # Créer une DB vide
        self._create_empty_index(target)
        log_to_stderr(f"  [AgentDB] index.sqlite <- nouveau (vide)\n")

    def save_index_to_cache(
        self,
        index_path: Path,
        branch_name: str,
        commit_sha: str,
        create_snapshot: bool = False
    ) -> bool:
        """
        Sauvegarde l'index dans le cache de la branche.

        Args:
            index_path: Chemin vers index.sqlite à sauvegarder
            branch_name: Nom de la branche
            commit_sha: SHA du commit
            create_snapshot: Créer aussi un snapshot

        Returns:
            True si sauvegardé
        """
        if not index_path.exists():
            return False

        cache = self.get_branch_cache(branch_name)
        cache.ensure_dirs()

        try:
            # Créer un snapshot de l'ancien état si demandé
            old_checkpoint = cache.get_checkpoint()
            if create_snapshot and old_checkpoint and cache.current_db.exists():
                cache.create_snapshot(old_checkpoint.commit)

            # Copier le nouvel index
            shutil.copy2(index_path, cache.current_db)

            # Mettre à jour le checkpoint
            checkpoint = BranchCheckpoint(
                commit=commit_sha,
                timestamp=time.time()
            )
            cache.set_checkpoint(checkpoint)

            log_to_stderr(f"  [AgentDB] Cache sauvegardé: {branch_name} @ {commit_sha[:12]}\n")
            return True

        except Exception as e:
            log_to_stderr(f"  [AgentDB] Erreur sauvegarde cache: {e}\n")
            return False

    def create_snapshot(self, branch_name: str, commit_sha: str) -> Optional[Path]:
        """Crée un snapshot pour un commit (utile avant merge)."""
        cache = self.get_branch_cache(branch_name)
        return cache.create_snapshot(commit_sha)

    def _create_shared_db(self, source_db: Path, target_db: Path) -> None:
        """Crée shared.sqlite avec seulement les tables partagées."""
        shared_tables = [
            "checkpoints", "error_history", "patterns",
            "architecture_decisions", "project_config",
        ]

        try:
            shutil.copy2(source_db, target_db)

            conn = sqlite3.connect(target_db)
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            all_tables = [row[0] for row in cursor.fetchall()]

            for table in all_tables:
                if table not in shared_tables and not table.startswith("sqlite_"):
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")

            conn.commit()
            conn.close()

            conn = sqlite3.connect(target_db)
            conn.execute("VACUUM")
            conn.close()

        except Exception as e:
            log_to_stderr(f"  [AgentDB] Erreur création shared.sqlite: {e}\n")
            shutil.copy2(source_db, target_db)

    def _create_empty_index(self, target_db: Path) -> None:
        """Crée un index.sqlite vide."""
        conn = sqlite3.connect(target_db)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                language TEXT,
                size INTEGER,
                last_modified TEXT,
                content_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT,
                file_id INTEGER REFERENCES files(id),
                line_start INTEGER,
                line_end INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
            CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
        """)
        conn.commit()
        conn.close()

    def list_branches(self) -> list[dict]:
        """Liste toutes les branches en cache."""
        branches_dir = self.cache_dir / "branches"
        if not branches_dir.exists():
            return []

        result = []
        for branch_dir in branches_dir.iterdir():
            if not branch_dir.is_dir():
                continue

            cache = BranchCache(self.cache_dir, branch_dir.name)
            checkpoint = cache.get_checkpoint()

            snapshots = list(cache.snapshots_dir.glob("*.sqlite")) if cache.snapshots_dir.exists() else []

            result.append({
                "branch": branch_dir.name,
                "commit": checkpoint.commit[:12] if checkpoint else None,
                "timestamp": checkpoint.timestamp if checkpoint else None,
                "snapshots": len(snapshots),
                "size_mb": cache.current_db.stat().st_size / (1024*1024) if cache.current_db.exists() else 0,
            })

        return result

    def cleanup_branch(self, branch_name: str) -> bool:
        """Supprime le cache d'une branche."""
        cache = self.get_branch_cache(branch_name)
        if cache.branch_dir.exists():
            shutil.rmtree(cache.branch_dir)
            log_to_stderr(f"  [AgentDB] Cache supprimé: {branch_name}\n")
            return True
        return False


# =============================================================================
# Factory
# =============================================================================

def get_agentdb_manager() -> AgentDBManager:
    """Factory pour obtenir une instance d'AgentDBManager."""
    return AgentDBManager()
