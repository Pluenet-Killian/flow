#!/usr/bin/env python3
"""
AgentDB Update - Mise à jour incrémentale.

Ce script met à jour AgentDB après des modifications de fichiers.
Il est conçu pour être appelé :
- Manuellement après des changements
- Automatiquement via un hook post-commit
- Par le pipeline CI

Il ne réindexe que les fichiers modifiés, pas tout le projet.

Usage:
    # Mise à jour automatique (détecte les changements depuis dernier commit)
    python -m scripts.update

    # Mise à jour de fichiers spécifiques
    python -m scripts.update file1.c file2.c

    # Depuis le dernier commit
    python -m scripts.update --since HEAD~1

Options:
    --since     Commit de référence pour détecter les changements
    --force     Forcer la réindexation même si le hash n'a pas changé
    --dry-run   Afficher ce qui serait fait sans l'exécuter
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# Ajouter le parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentdb import Database
from agentdb.indexer import CodeIndexer
from agentdb.crud import FileRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("update")


# =============================================================================
# UPDATE RUNNER
# =============================================================================

class UpdateRunner:
    """
    Gère la mise à jour incrémentale d'AgentDB.
    """

    def __init__(
        self,
        project_root: Path,
        db_path: Optional[Path] = None
    ) -> None:
        """
        Initialise le runner.

        Args:
            project_root: Racine du projet
            db_path: Chemin vers la DB (défaut: .claude/agentdb/db.sqlite)
        """
        self.project_root = project_root
        self.db_path = db_path or (project_root / ".claude" / "agentdb" / "db.sqlite")

        self.db: Optional[Database] = None
        self.indexer: Optional[CodeIndexer] = None
        self.files_repo: Optional[FileRepository] = None

    def connect(self) -> None:
        """Connecte à la base de données."""
        # TODO: Implémenter
        pass

    def close(self) -> None:
        """Ferme la connexion."""
        # TODO: Implémenter
        pass

    # -------------------------------------------------------------------------
    # DETECT CHANGES
    # -------------------------------------------------------------------------

    def get_changed_files_git(self, since: str = "HEAD~1") -> list[str]:
        """
        Détecte les fichiers modifiés via Git.

        Args:
            since: Commit de référence

        Returns:
            Liste des chemins modifiés
        """
        # TODO: Implémenter
        # git diff --name-only <since>
        # Filtrer par extensions indexables
        pass

    def get_changed_files_hash(self) -> list[str]:
        """
        Détecte les fichiers modifiés via comparaison de hash.

        Compare le hash actuel avec celui stocké dans AgentDB.

        Returns:
            Liste des chemins dont le hash a changé
        """
        # TODO: Implémenter
        # Pour chaque fichier dans files:
        #   Calculer le hash actuel
        #   Comparer avec content_hash
        pass

    def detect_new_files(self) -> list[str]:
        """
        Détecte les nouveaux fichiers (pas encore dans AgentDB).

        Returns:
            Liste des nouveaux fichiers
        """
        # TODO: Implémenter
        # Lister les fichiers du projet
        # Comparer avec ceux dans files
        pass

    def detect_deleted_files(self) -> list[str]:
        """
        Détecte les fichiers supprimés.

        Returns:
            Liste des fichiers dans AgentDB mais plus sur le disque
        """
        # TODO: Implémenter
        pass

    # -------------------------------------------------------------------------
    # UPDATE OPERATIONS
    # -------------------------------------------------------------------------

    def update_files(
        self,
        file_paths: list[str],
        force: bool = False,
        dry_run: bool = False
    ) -> dict[str, Any]:
        """
        Met à jour les fichiers spécifiés.

        Args:
            file_paths: Liste des chemins à mettre à jour
            force: Forcer même si hash identique
            dry_run: Ne pas exécuter

        Returns:
            Rapport de mise à jour
        """
        # TODO: Implémenter
        # Pour chaque fichier:
        #   1. Supprimer anciens symboles/relations
        #   2. Réindexer
        #   3. Mettre à jour les métriques
        result = {
            "updated": [],
            "added": [],
            "removed": [],
            "errors": [],
            "skipped": []
        }
        return result

    def add_files(self, file_paths: list[str]) -> dict[str, Any]:
        """
        Ajoute de nouveaux fichiers à l'index.

        Args:
            file_paths: Chemins des nouveaux fichiers

        Returns:
            Rapport
        """
        # TODO: Implémenter
        pass

    def remove_files(self, file_paths: list[str]) -> dict[str, Any]:
        """
        Supprime des fichiers de l'index.

        Args:
            file_paths: Chemins des fichiers supprimés

        Returns:
            Rapport
        """
        # TODO: Implémenter
        pass

    # -------------------------------------------------------------------------
    # FULL UPDATE
    # -------------------------------------------------------------------------

    def run_auto_update(
        self,
        since: Optional[str] = None,
        force: bool = False,
        dry_run: bool = False
    ) -> dict[str, Any]:
        """
        Exécute une mise à jour automatique.

        Détecte les changements et met à jour en conséquence.

        Args:
            since: Commit de référence (défaut: depuis le dernier index)
            force: Forcer la réindexation
            dry_run: Mode simulation

        Returns:
            Rapport complet
        """
        logger.info("Starting auto-update...")

        self.connect()

        try:
            # Détecter les changements
            if since:
                changed = self.get_changed_files_git(since)
            else:
                changed = self.get_changed_files_hash()

            new_files = self.detect_new_files()
            deleted = self.detect_deleted_files()

            logger.info(f"Detected: {len(changed)} modified, {len(new_files)} new, {len(deleted)} deleted")

            if dry_run:
                return {
                    "dry_run": True,
                    "would_update": changed,
                    "would_add": new_files,
                    "would_remove": deleted
                }

            # Exécuter les mises à jour
            result = {
                "updated": [],
                "added": [],
                "removed": [],
                "errors": []
            }

            if deleted:
                r = self.remove_files(deleted)
                result["removed"] = r.get("removed", [])

            if new_files:
                r = self.add_files(new_files)
                result["added"] = r.get("added", [])

            if changed:
                r = self.update_files(changed, force=force)
                result["updated"] = r.get("updated", [])

            return result

        finally:
            self.close()

    def run_specific_update(
        self,
        file_paths: list[str],
        force: bool = False,
        dry_run: bool = False
    ) -> dict[str, Any]:
        """
        Met à jour des fichiers spécifiques.

        Args:
            file_paths: Liste des chemins
            force: Forcer la réindexation
            dry_run: Mode simulation

        Returns:
            Rapport
        """
        logger.info(f"Updating {len(file_paths)} specific files...")

        if dry_run:
            return {"dry_run": True, "would_update": file_paths}

        self.connect()
        try:
            return self.update_files(file_paths, force=force)
        finally:
            self.close()


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    """Point d'entrée CLI."""
    parser = argparse.ArgumentParser(
        description="Incremental update of AgentDB"
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific files to update (optional)"
    )
    parser.add_argument(
        "--since", "-s",
        help="Git commit reference for change detection"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force reindexing even if hash unchanged"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without doing it"
    )
    parser.add_argument(
        "--project", "-p",
        type=Path,
        default=Path.cwd(),
        help="Project root directory"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        runner = UpdateRunner(project_root=args.project)

        if args.files:
            result = runner.run_specific_update(
                args.files,
                force=args.force,
                dry_run=args.dry_run
            )
        else:
            result = runner.run_auto_update(
                since=args.since,
                force=args.force,
                dry_run=args.dry_run
            )

        # Afficher le résultat
        if args.dry_run:
            logger.info("Dry run - no changes made")
            if result.get("would_update"):
                logger.info(f"Would update: {result['would_update']}")
            if result.get("would_add"):
                logger.info(f"Would add: {result['would_add']}")
            if result.get("would_remove"):
                logger.info(f"Would remove: {result['would_remove']}")
        else:
            logger.info(f"Updated: {len(result.get('updated', []))} files")
            logger.info(f"Added: {len(result.get('added', []))} files")
            logger.info(f"Removed: {len(result.get('removed', []))} files")

        return 0 if not result.get("errors") else 1

    except Exception as e:
        logger.error(f"Update failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
