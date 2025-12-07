"""
AgentDB - Indexeur de code source.

Ce module est responsable de :
- Parser les fichiers source pour extraire les symboles
- Détecter les relations entre symboles (appels, includes, etc.)
- Calculer les métriques de code (complexité, lignes, etc.)
- Analyser l'historique Git (activité, contributeurs)
- Détecter les fichiers critiques

Parsers supportés :
- C/C++ : ctags (universel) ou tree-sitter (précis)
- Python : module ast (natif)
- JavaScript/TypeScript : tree-sitter

Usage:
    indexer = CodeIndexer(db, config)

    # Indexer un seul fichier
    indexer.index_file("src/main.c")

    # Indexer tout le projet
    indexer.index_project()

    # Mise à jour incrémentale
    indexer.update_files(["src/modified.c", "src/new.c"])
"""

from __future__ import annotations

import hashlib
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .db import Database
from .models import File, Symbol, Relation, FileRelation, SymbolKind, RelationType
from .crud import FileRepository, SymbolRepository, RelationRepository, FileRelationRepository


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class IndexerConfig:
    """
    Configuration de l'indexeur.
    """
    # Racine du projet
    project_root: Path = Path(".")

    # Extensions à indexer par langage
    extensions: dict[str, list[str]] = None

    # Patterns à exclure
    exclude_patterns: list[str] = None

    # Outil d'indexation par langage
    tools: dict[str, str] = None

    # Chemins critiques
    critical_paths: list[str] = None

    # Chemins haute importance
    high_importance_paths: list[str] = None

    def __post_init__(self):
        if self.extensions is None:
            self.extensions = {
                "c": [".c", ".h"],
                "cpp": [".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx"],
                "python": [".py"],
                "javascript": [".js", ".jsx", ".ts", ".tsx"],
            }
        if self.exclude_patterns is None:
            self.exclude_patterns = [
                "build/**", "dist/**", "vendor/**", "node_modules/**",
                "**/*.min.js", "**/*.generated.*", ".git/**", ".claude/agentdb/**"
            ]
        if self.tools is None:
            self.tools = {
                "c": "ctags",
                "cpp": "ctags",
                "python": "ast",
                "javascript": "tree-sitter"
            }
        if self.critical_paths is None:
            self.critical_paths = [
                "src/security/**", "src/auth/**", "src/crypto/**",
                "**/password*", "**/secret*"
            ]
        if self.high_importance_paths is None:
            self.high_importance_paths = [
                "src/core/**", "src/api/**", "src/main.*"
            ]


# =============================================================================
# LANGUAGE PARSERS
# =============================================================================

class LanguageParser(ABC):
    """
    Parser abstrait pour un langage.
    """

    @property
    @abstractmethod
    def language(self) -> str:
        """Nom du langage."""
        pass

    @abstractmethod
    def parse_file(self, file_path: Path) -> tuple[list[Symbol], list[Relation]]:
        """
        Parse un fichier et extrait symboles et relations.

        Args:
            file_path: Chemin du fichier

        Returns:
            Tuple (symboles, relations)
        """
        pass

    @abstractmethod
    def calculate_complexity(self, content: str) -> dict[str, int]:
        """
        Calcule les métriques de complexité.

        Args:
            content: Contenu du fichier

        Returns:
            Dict avec cyclomatic, cognitive, nesting_depth
        """
        pass


class CTagsParser(LanguageParser):
    """
    Parser utilisant Universal Ctags pour C/C++.
    """

    @property
    def language(self) -> str:
        return "c"

    def parse_file(self, file_path: Path) -> tuple[list[Symbol], list[Relation]]:
        """
        Parse un fichier C/C++ avec ctags.

        Args:
            file_path: Chemin du fichier

        Returns:
            (symbols, relations) - Relations vides (ctags ne les extrait pas)
        """
        # TODO: Implémenter l'appel à ctags
        # ctags --output-format=json --fields=+neKS -o - <file>
        # Parser le JSON et créer les Symbol
        pass

    def calculate_complexity(self, content: str) -> dict[str, int]:
        """
        Calcule la complexité cyclomatique pour C.

        Compte les points de décision :
        - if, else if
        - for, while, do-while
        - switch case
        - && ||
        - ? :
        """
        # TODO: Implémenter le comptage
        pass


class PythonASTParser(LanguageParser):
    """
    Parser utilisant le module ast pour Python.
    """

    @property
    def language(self) -> str:
        return "python"

    def parse_file(self, file_path: Path) -> tuple[list[Symbol], list[Relation]]:
        """
        Parse un fichier Python avec ast.

        Args:
            file_path: Chemin du fichier

        Returns:
            (symbols, relations)
        """
        # TODO: Implémenter avec ast.parse
        # Extraire: FunctionDef, AsyncFunctionDef, ClassDef, Import, ImportFrom
        # Pour les relations: analyser les appels (Call nodes)
        pass

    def calculate_complexity(self, content: str) -> dict[str, int]:
        """
        Calcule la complexité pour Python avec ast.
        """
        # TODO: Implémenter avec ast.NodeVisitor
        pass


class TreeSitterParser(LanguageParser):
    """
    Parser utilisant tree-sitter (multi-langage).
    """

    def __init__(self, language: str):
        self._language = language

    @property
    def language(self) -> str:
        return self._language

    def parse_file(self, file_path: Path) -> tuple[list[Symbol], list[Relation]]:
        """
        Parse un fichier avec tree-sitter.
        """
        # TODO: Implémenter avec tree-sitter
        # Nécessite les grammaires tree-sitter installées
        pass

    def calculate_complexity(self, content: str) -> dict[str, int]:
        """
        Calcule la complexité avec tree-sitter.
        """
        # TODO: Implémenter
        pass


# =============================================================================
# MAIN INDEXER
# =============================================================================

class CodeIndexer:
    """
    Indexeur principal de code source.

    Orchestre le parsing, l'extraction de métriques,
    et l'insertion dans AgentDB.
    """

    def __init__(self, db: Database, config: Optional[IndexerConfig] = None) -> None:
        """
        Initialise l'indexeur.

        Args:
            db: Connexion à la base AgentDB
            config: Configuration (utilise les défauts si None)
        """
        self.db = db
        self.config = config or IndexerConfig()

        # Repositories
        self.files = FileRepository(db)
        self.symbols = SymbolRepository(db)
        self.relations = RelationRepository(db)
        self.file_relations = FileRelationRepository(db)

        # Parsers par langage
        self.parsers: dict[str, LanguageParser] = {}
        self._init_parsers()

    def _init_parsers(self) -> None:
        """Initialise les parsers selon la configuration."""
        # TODO: Créer les parsers selon config.tools
        pass

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def index_project(self) -> dict[str, Any]:
        """
        Indexe tout le projet.

        Returns:
            Rapport d'indexation {files_indexed, symbols, relations, errors}
        """
        # TODO: Implémenter
        # 1. Lister tous les fichiers (respecter exclusions)
        # 2. Pour chaque fichier: index_file()
        # 3. Analyser l'activité Git
        # 4. Marquer les fichiers critiques
        # 5. Retourner le rapport
        pass

    def index_file(self, file_path: str) -> Optional[int]:
        """
        Indexe un seul fichier.

        Args:
            file_path: Chemin relatif du fichier

        Returns:
            ID du fichier ou None si erreur
        """
        # TODO: Implémenter
        # 1. Vérifier si le fichier doit être indexé
        # 2. Lire et hasher le contenu
        # 3. Détecter le langage
        # 4. Parser avec le bon parser
        # 5. Calculer les métriques
        # 6. Insérer/màj dans files
        # 7. Insérer les symboles
        # 8. Insérer les relations
        pass

    def update_files(self, file_paths: list[str]) -> dict[str, Any]:
        """
        Met à jour l'index pour une liste de fichiers.

        Args:
            file_paths: Liste des chemins modifiés

        Returns:
            Rapport de mise à jour
        """
        # TODO: Implémenter
        # Pour chaque fichier:
        # 1. Supprimer les anciens symboles/relations
        # 2. Réindexer le fichier
        pass

    def remove_file(self, file_path: str) -> bool:
        """
        Supprime un fichier de l'index.

        Args:
            file_path: Chemin du fichier

        Returns:
            True si supprimé
        """
        # TODO: Implémenter
        # 1. Supprimer les relations
        # 2. Supprimer les symboles
        # 3. Supprimer le fichier
        pass

    # -------------------------------------------------------------------------
    # FILE ANALYSIS
    # -------------------------------------------------------------------------

    def _should_index(self, file_path: Path) -> bool:
        """
        Vérifie si un fichier doit être indexé.

        Args:
            file_path: Chemin du fichier

        Returns:
            True si le fichier doit être indexé
        """
        # TODO: Vérifier extension et exclusions
        pass

    def _detect_language(self, file_path: Path) -> Optional[str]:
        """
        Détecte le langage d'un fichier.

        Args:
            file_path: Chemin du fichier

        Returns:
            Nom du langage ou None
        """
        # TODO: Basé sur l'extension
        pass

    def _detect_module(self, file_path: Path) -> Optional[str]:
        """
        Déduit le module d'un fichier depuis son chemin.

        Ex: src/lcd/init.c -> "lcd"

        Args:
            file_path: Chemin du fichier

        Returns:
            Nom du module
        """
        # TODO: Parser le chemin
        pass

    def _detect_file_type(self, file_path: Path) -> str:
        """
        Détermine le type de fichier.

        Args:
            file_path: Chemin du fichier

        Returns:
            "source", "header", "test", "config", ou "doc"
        """
        # TODO: Basé sur le nom et l'extension
        pass

    def _calculate_hash(self, content: str) -> str:
        """
        Calcule le hash SHA256 du contenu.

        Args:
            content: Contenu du fichier

        Returns:
            Hash hexadécimal
        """
        return hashlib.sha256(content.encode()).hexdigest()

    def _count_lines(self, content: str) -> dict[str, int]:
        """
        Compte les lignes de code, commentaires, et blanches.

        Args:
            content: Contenu du fichier

        Returns:
            Dict avec total, code, comment, blank
        """
        # TODO: Implémenter le comptage intelligent
        pass

    # -------------------------------------------------------------------------
    # GIT ANALYSIS
    # -------------------------------------------------------------------------

    def analyze_git_activity(self, file_path: Optional[str] = None) -> None:
        """
        Analyse l'activité Git pour les fichiers.

        Args:
            file_path: Fichier spécifique (ou tous si None)
        """
        # TODO: Implémenter avec git log
        pass

    def _get_commit_counts(self, file_path: str) -> dict[str, int]:
        """
        Compte les commits sur différentes périodes.

        Args:
            file_path: Chemin du fichier

        Returns:
            Dict avec commits_30d, commits_90d, commits_365d
        """
        # TODO: Exécuter git log avec --since
        pass

    def _get_contributors(self, file_path: str) -> list[dict[str, Any]]:
        """
        Récupère les contributeurs d'un fichier.

        Args:
            file_path: Chemin du fichier

        Returns:
            Liste de {name, email, commits}
        """
        # TODO: Exécuter git log --format
        pass

    def _get_last_modified(self, file_path: str) -> Optional[str]:
        """
        Récupère la date de dernière modification.

        Args:
            file_path: Chemin du fichier

        Returns:
            Date ISO ou None
        """
        # TODO: Exécuter git log -1 --format
        pass

    # -------------------------------------------------------------------------
    # CRITICALITY DETECTION
    # -------------------------------------------------------------------------

    def detect_criticality(self, file_path: Optional[str] = None) -> None:
        """
        Détecte et marque les fichiers critiques.

        Args:
            file_path: Fichier spécifique (ou tous si None)
        """
        # TODO: Implémenter avec les patterns de config
        pass

    def _is_critical_path(self, file_path: str) -> tuple[bool, Optional[str]]:
        """
        Vérifie si un fichier est dans un chemin critique.

        Args:
            file_path: Chemin du fichier

        Returns:
            (is_critical, reason)
        """
        # TODO: Matcher contre critical_paths
        pass

    def _is_security_sensitive(self, file_path: str, content: str) -> bool:
        """
        Vérifie si un fichier est sensible du point de vue sécurité.

        Args:
            file_path: Chemin du fichier
            content: Contenu du fichier

        Returns:
            True si sensible
        """
        # TODO: Vérifier les patterns de nom et le contenu
        pass

    # -------------------------------------------------------------------------
    # INCLUDE/IMPORT ANALYSIS
    # -------------------------------------------------------------------------

    def extract_file_relations(self, file_path: str, content: str) -> list[FileRelation]:
        """
        Extrait les relations de fichiers (includes/imports).

        Args:
            file_path: Chemin du fichier
            content: Contenu du fichier

        Returns:
            Liste de FileRelation
        """
        # TODO: Parser les #include et import selon le langage
        pass

    def _extract_c_includes(self, content: str) -> list[str]:
        """
        Extrait les #include d'un fichier C/C++.

        Args:
            content: Contenu du fichier

        Returns:
            Liste des fichiers inclus
        """
        # TODO: Regex sur #include "..." et #include <...>
        pass

    def _extract_python_imports(self, content: str) -> list[str]:
        """
        Extrait les imports d'un fichier Python.

        Args:
            content: Contenu du fichier

        Returns:
            Liste des modules importés
        """
        # TODO: ast.parse et chercher Import/ImportFrom
        pass


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def run_ctags(file_path: Path) -> list[dict[str, Any]]:
    """
    Exécute ctags sur un fichier et retourne les tags.

    Args:
        file_path: Chemin du fichier

    Returns:
        Liste des tags au format dict
    """
    # TODO: Implémenter l'appel subprocess
    pass


def parse_ctags_json(output: str) -> list[dict[str, Any]]:
    """
    Parse la sortie JSON de ctags.

    Args:
        output: Sortie JSON de ctags

    Returns:
        Liste des tags parsés
    """
    # TODO: Implémenter le parsing
    pass
