"""
AgentDB MCP Server v6 "Lean" - Serveur optimisé pour compléter LSP.

Ce module implémente le serveur MCP qui expose UNIQUEMENT les fonctionnalités
que LSP ne fournit pas nativement dans Claude Code.

Architecture v6 "Lean":
- 12 outils MCP focalisés sur la valeur ajoutée
- LSP natif pour: navigation, références, call hierarchy, symbols
- AgentDB pour: contexte historique, sémantique, learning, métriques

Outils supprimés (redondants avec LSP):
- get_symbol_callers -> LSP incomingCalls
- get_symbol_callees -> LSP outgoingCalls
- get_file_impact -> LSP findReferences + enrichissement minimal
- search_symbols -> LSP workspaceSymbol
- smart_references -> LSP findReferences
- smart_callers -> LSP incomingCalls
- impact_analysis_v2 -> LSP + get_risk_assessment
- smart_search -> LSP workspaceSymbol
- parse_file -> LSP documentSymbol
- get_supported_languages -> Non nécessaire runtime
- get_embedding_stats -> Debug only
- get_learning_stats -> Debug only

Usage:
    python -m mcp.agentdb.server
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Union

# Ajouter le path pour les imports locaux
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Configuration du logging
logging.basicConfig(
    level=os.environ.get("AGENTDB_LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("agentdb.mcp.server")


# =============================================================================
# CONSTANTS
# =============================================================================

SERVER_VERSION = "6.0.0"  # v6 Lean - Optimisé pour compléter LSP
SERVER_NAME = "agentdb"

# Codes d'erreur JSON-RPC
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Erreurs spécifiques AgentDB
TOOL_NOT_FOUND = -32000
DATABASE_ERROR = -32001
SYMBOL_NOT_FOUND = -32002
FILE_NOT_FOUND = -32003


# =============================================================================
# TOOL DEFINITIONS v6 LEAN (12 outils)
# =============================================================================

TOOL_DEFINITIONS = [
    # =========================================================================
    # CONTEXTE & HISTORIQUE (Ce que LSP ne sait pas)
    # =========================================================================

    # 1. get_file_context - Vue 360° d'un fichier
    {
        "name": "get_file_context",
        "description": """Contexte complet d'un fichier : métadonnées, historique d'erreurs,
métriques de code, et patterns applicables.

QUAND L'UTILISER: Avant de modifier un fichier, pour comprendre son contexte.

NOTE: Pour les symboles et dépendances, utilisez LSP:
- LSP documentSymbol: liste des symboles
- LSP findReferences: qui utilise ce fichier

Ce que cet outil ajoute vs LSP:
- Historique des bugs/erreurs passés
- Métriques (complexité, lignes, risque)
- Patterns de code à respecter
- Activité Git (qui, quand, combien)

Exemple:
{
  "file": {"path": "src/lcd/init.c", "module": "lcd", "language": "c"},
  "error_history": [{"type": "null_pointer", "date": "2024-01-15", "fixed": true}],
  "metrics": {"complexity": 15, "lines_code": 127, "risk_score": 0.6},
  "git_activity": {"commits_30d": 5, "contributors": ["alice", "bob"]},
  "patterns": [{"name": "error_handling", "description": "..."}]
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Chemin du fichier"
                },
                "include_history": {
                    "type": "boolean",
                    "default": True,
                    "description": "Inclure l'historique des erreurs"
                },
                "include_patterns": {
                    "type": "boolean",
                    "default": True,
                    "description": "Inclure les patterns applicables"
                }
            },
            "required": ["path"]
        }
    },

    # 2. get_error_history - Historique des erreurs
    {
        "name": "get_error_history",
        "description": """Historique des bugs/erreurs associés à un fichier, symbole, ou module.

QUAND L'UTILISER: Pour identifier les zones à risque, comprendre les problèmes récurrents.

Ce que LSP ne fait pas:
- Mémoire des bugs passés
- Corrélation erreur/fichier/symbole
- Statistiques de fiabilité

Exemple:
{
  "errors": [
    {
      "type": "buffer_overflow",
      "severity": "critical",
      "description": "Overflow dans lcd_write_string",
      "date_reported": "2024-01-15",
      "date_fixed": "2024-01-16",
      "symbol_name": "lcd_write_string"
    }
  ],
  "summary": {"total": 3, "by_type": {"buffer_overflow": 1, "null_pointer": 2}}
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Filtrer par fichier"},
                "symbol_name": {"type": "string", "description": "Filtrer par symbole"},
                "module": {"type": "string", "description": "Filtrer par module"},
                "error_type": {"type": "string", "description": "Type d'erreur"},
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low"]
                },
                "days": {"type": "integer", "default": 180},
                "limit": {"type": "integer", "default": 20}
            }
        }
    },

    # 3. get_patterns - Patterns de code
    {
        "name": "get_patterns",
        "description": """Patterns et conventions de code applicables à un fichier/module.

QUAND L'UTILISER: Avant d'écrire du code, pour respecter les conventions du projet.

Ce que LSP ne fait pas:
- Documentation des conventions de code
- Patterns métier spécifiques
- Exemples de code à suivre

Exemple:
{
  "patterns": [
    {
      "name": "error_handling",
      "category": "reliability",
      "description": "Retourner un code d'erreur, jamais NULL",
      "example": "int lcd_init() { if (!cfg) return LCD_ERR_NULL; }"
    }
  ]
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "module": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": ["error_handling", "memory", "naming", "documentation", "security", "performance"]
                },
                "include_examples": {"type": "boolean", "default": True}
            }
        }
    },

    # 4. get_architecture_decisions - ADRs
    {
        "name": "get_architecture_decisions",
        "description": """Architecture Decision Records (ADR) applicables.

QUAND L'UTILISER: Pour comprendre POURQUOI le code est structuré ainsi.

Ce que LSP ne fait pas:
- Mémoire des décisions architecturales
- Contexte et alternatives considérées
- Conséquences documentées

Exemple:
{
  "decisions": [
    {
      "id": "ADR-003",
      "title": "Double buffering pour LCD",
      "status": "accepted",
      "context": "L'affichage direct cause du scintillement",
      "decision": "Implémenter un double buffering",
      "consequences": "Mémoire doublée mais affichage fluide"
    }
  ]
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module": {"type": "string"},
                "file_path": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["accepted", "proposed", "deprecated", "superseded"],
                    "default": "accepted"
                }
            }
        }
    },

    # =========================================================================
    # MÉTRIQUES & RISQUE (Analyse quantitative)
    # =========================================================================

    # 5. get_file_metrics - Métriques détaillées
    {
        "name": "get_file_metrics",
        "description": """Métriques détaillées et score de risque d'un fichier.

QUAND L'UTILISER: Pour évaluer la qualité/complexité avant modification.

Ce que LSP ne fait pas:
- Complexité cyclomatique
- Score de risque calculé
- Activité Git historique
- Corrélation métriques/bugs

Exemple:
{
  "metrics": {
    "lines": {"total": 250, "code": 180, "comment": 45},
    "complexity": {"sum": 45, "avg": 9, "max": 18},
    "git": {"commits_30d": 5, "contributors": ["alice"]},
    "risk_score": 0.65,
    "risk_factors": ["high_complexity", "frequent_changes"]
  }
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du fichier"},
                "include_per_function": {"type": "boolean", "default": False}
            },
            "required": ["path"]
        }
    },

    # 6. get_module_summary - Résumé d'un module
    {
        "name": "get_module_summary",
        "description": """Résumé complet d'un module (ensemble de fichiers).

QUAND L'UTILISER: Pour comprendre un module entier rapidement.

Ce que LSP ne fait pas:
- Agrégation par module
- Statistiques globales
- Santé du module (bugs, couverture)
- Dépendances inter-modules

Exemple:
{
  "module": "lcd",
  "files": ["init.c", "write.c", "types.h"],
  "stats": {"total_files": 5, "total_lines": 850, "avg_complexity": 8.5},
  "dependencies": {"uses": ["hal"], "used_by": ["ui"]},
  "health": {"error_count_90d": 3, "risk_score": 0.4}
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module": {"type": "string", "description": "Nom du module"},
                "include_private": {"type": "boolean", "default": False}
            },
            "required": ["module"]
        }
    },

    # 7. get_risk_assessment - Évaluation de risque multi-fichiers
    {
        "name": "get_risk_assessment",
        "description": """Évalue le risque d'un ensemble de modifications (pour PR review).

QUAND L'UTILISER: Avant de merger une PR, pour évaluer le risque global.

Ce que LSP ne fait pas:
- Score de risque agrégé
- Identification des fichiers critiques
- Recommandations basées sur l'historique

Exemple:
{
  "files": [
    {"file": "src/core.py", "risk_score": 65, "is_critical": true},
    {"file": "src/utils.py", "risk_score": 20}
  ],
  "overall_risk_score": 42.5,
  "risk_factors": ["Critical file modified", "High complexity"],
  "recommendations": ["Review core.py changes carefully", "Add tests"]
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste des fichiers modifiés"
                },
                "include_recommendations": {"type": "boolean", "default": True}
            },
            "required": ["file_paths"]
        }
    },

    # =========================================================================
    # RECHERCHE SÉMANTIQUE (Ce que LSP ne peut pas faire)
    # =========================================================================

    # 8. semantic_search - Recherche en langage naturel
    {
        "name": "semantic_search",
        "description": """Recherche de code par description en langage naturel.

QUAND L'UTILISER: Quand vous ne connaissez pas le nom exact.
- "Trouve les fonctions qui gèrent l'authentification"
- "Code qui parse du JSON"
- "Fonctions de validation d'input"

Ce que LSP ne fait pas:
- Comprendre le langage naturel
- Recherche par sémantique/concept
- Trouver du code similaire par intention

Pour recherche par nom exact: utilisez LSP workspaceSymbol.

Exemple:
{
  "query": "user authentication",
  "results": [
    {"name": "verify_credentials", "similarity": 0.87, "file": "auth/login.py"},
    {"name": "check_session", "similarity": 0.72, "file": "auth/session.py"}
  ]
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Description en langage naturel"
                },
                "search_type": {
                    "type": "string",
                    "enum": ["symbols", "files"],
                    "default": "symbols"
                },
                "top_k": {"type": "integer", "default": 10, "maximum": 50},
                "threshold": {"type": "number", "default": 0.3, "minimum": 0, "maximum": 1},
                "kind": {"type": "string", "description": "Type de symbole"},
                "module": {"type": "string"}
            },
            "required": ["query"]
        }
    },

    # 9. find_similar_code - Trouver du code similaire
    {
        "name": "find_similar_code",
        "description": """Trouve du code sémantiquement similaire à un symbole donné.

QUAND L'UTILISER:
- Refactoring: trouver du code à factoriser
- Détecter les duplications
- Trouver des implémentations alternatives

Ce que LSP ne fait pas:
- Comparer la sémantique du code
- Détecter les quasi-duplications
- Suggérer du code à factoriser

Exemple:
{
  "symbol_id": 123,
  "similar": [
    {"name": "validate_user_input", "similarity": 0.89, "file": "forms/validator.py"},
    {"name": "check_form_data", "similarity": 0.76, "file": "api/validators.py"}
  ]
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol_id": {
                    "type": "integer",
                    "description": "ID du symbole (obtenu via semantic_search)"
                },
                "top_k": {"type": "integer", "default": 10},
                "threshold": {"type": "number", "default": 0.5}
            },
            "required": ["symbol_id"]
        }
    },

    # =========================================================================
    # PATTERN LEARNING (Apprentissage automatique)
    # =========================================================================

    # 10. learn_from_history - Apprendre depuis Git
    {
        "name": "learn_from_history",
        "description": """Apprend des patterns d'erreurs depuis l'historique Git.

QUAND L'UTILISER: Périodiquement, pour améliorer les détections.

Ce que LSP ne fait pas:
- Analyser l'historique des commits "fix"
- Identifier les patterns d'erreurs récurrents
- Apprendre des corrections passées

Exemple:
{
  "commits_analyzed": 150,
  "fixes_found": 23,
  "patterns_learned": 5,
  "patterns": [
    {"name": "null_check_missing", "confidence": 0.85, "occurrences": 8}
  ]
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 90},
                "min_fixes": {"type": "integer", "default": 2}
            }
        }
    },

    # 11. detect_code_smells - Détecter les anti-patterns
    {
        "name": "detect_code_smells",
        "description": """Détecte les code smells et anti-patterns.

QUAND L'UTILISER: Pour audit de qualité, avant refactoring.

Types détectés:
- long_method: Méthodes > 50 lignes
- god_class: Classes > 20 méthodes
- high_complexity: Complexité > 15
- large_file: Fichiers > 1000 lignes

Ce que LSP ne fait pas:
- Analyse qualitative du code
- Détection d'anti-patterns
- Suggestions d'amélioration

Exemple:
{
  "smells": [
    {
      "type": "long_method",
      "severity": "medium",
      "symbol": "process_request",
      "line": 45,
      "suggestion": "Divisez en sous-méthodes"
    }
  ]
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Fichier (ou tous si omis)"},
                "save_to_db": {"type": "boolean", "default": True}
            }
        }
    },

    # 12. get_suggestions - Suggestions d'amélioration
    {
        "name": "get_suggestions",
        "description": """Suggestions d'amélioration pour un fichier.

QUAND L'UTILISER: Pendant la code review, pour améliorer la qualité.

Combine:
- Patterns appris depuis l'historique
- Code smells détectés
- Conventions du projet

Ce que LSP ne fait pas:
- Recommandations personnalisées
- Apprentissage continu
- Contexte historique

Exemple:
{
  "file_path": "src/core/engine.py",
  "patterns": [{"name": "null_check", "confidence": 0.85}],
  "smells": [{"type": "high_complexity", "severity": "high"}],
  "summary": {"total": 5, "by_severity": {"high": 2, "medium": 3}}
}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "include_patterns": {"type": "boolean", "default": True},
                "include_smells": {"type": "boolean", "default": True}
            },
            "required": ["file_path"]
        }
    },
]


# =============================================================================
# MCP SERVER CLASS
# =============================================================================

class AgentDBServer:
    """
    Serveur MCP v6 Lean pour AgentDB.

    12 outils focalisés sur ce que LSP ne fait pas:
    - Contexte historique (bugs, patterns, ADRs)
    - Métriques et risque
    - Recherche sémantique
    - Pattern learning
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        config_path: Optional[str] = None
    ) -> None:
        self.db_path = db_path or os.environ.get(
            "AGENTDB_PATH",
            ".claude/agentdb/db.sqlite"
        )
        self.config_path = config_path or os.environ.get(
            "AGENTDB_CONFIG",
            ".claude/config/agentdb.yaml"
        )

        self.db = None
        self.config = None
        self._initialized = False
        self.tool_handlers: dict[str, Callable] = {}

        logger.debug(f"AgentDBServer v6 Lean created with db_path={self.db_path}")

    def initialize(self) -> None:
        """Initialise la connexion DB et les handlers."""
        if self._initialized:
            return

        logger.info(f"Initializing AgentDB server v6 Lean...")
        logger.info(f"  Database: {self.db_path}")

        # Charger la configuration
        try:
            from agentdb.config import load_config
            self.config = load_config(self.config_path)
        except Exception as e:
            logger.warning(f"Could not load config: {e}, using defaults")
            self.config = None

        # Connecter à la base de données
        try:
            from agentdb.db import DatabaseManager
            self.db = DatabaseManager(self.db_path)
            self.db.connect()
            logger.info("  Database connected")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

        # Enregistrer les handlers (12 outils seulement)
        self._register_handlers()

        self._initialized = True
        logger.info(f"AgentDB server v6 Lean initialized - {len(self.tool_handlers)} tools")

    def _register_handlers(self) -> None:
        """Enregistre les 12 handlers lean."""
        self.tool_handlers = {
            # Contexte & Historique (4 outils)
            "get_file_context": self._handle_get_file_context,
            "get_error_history": self._handle_get_error_history,
            "get_patterns": self._handle_get_patterns,
            "get_architecture_decisions": self._handle_get_architecture_decisions,
            # Métriques & Risque (3 outils)
            "get_file_metrics": self._handle_get_file_metrics,
            "get_module_summary": self._handle_get_module_summary,
            "get_risk_assessment": self._handle_get_risk_assessment,
            # Recherche Sémantique (2 outils)
            "semantic_search": self._handle_semantic_search,
            "find_similar_code": self._handle_find_similar_code,
            # Pattern Learning (3 outils)
            "learn_from_history": self._handle_learn_from_history,
            "detect_code_smells": self._handle_detect_code_smells,
            "get_suggestions": self._handle_get_suggestions,
        }

    # =========================================================================
    # HANDLERS - Contexte & Historique
    # =========================================================================

    async def _handle_get_file_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_file_context (simplifié, sans symboles/deps - utiliser LSP)."""
        from . import tools
        return tools.get_file_context(
            self.db,
            path=arguments["path"],
            include_symbols=False,  # LSP documentSymbol
            include_dependencies=False,  # LSP findReferences
            include_history=arguments.get("include_history", True),
            include_patterns=arguments.get("include_patterns", True),
        )

    async def _handle_get_error_history(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_error_history."""
        from . import tools
        return tools.get_error_history(
            self.db,
            file_path=arguments.get("file_path"),
            symbol_name=arguments.get("symbol_name"),
            module=arguments.get("module"),
            error_type=arguments.get("error_type"),
            severity=arguments.get("severity"),
            days=arguments.get("days", 180),
            limit=arguments.get("limit", 20),
        )

    async def _handle_get_patterns(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_patterns."""
        from . import tools
        return tools.get_patterns(
            self.db,
            file_path=arguments.get("file_path"),
            module=arguments.get("module"),
            category=arguments.get("category"),
            include_examples=arguments.get("include_examples", True),
        )

    async def _handle_get_architecture_decisions(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_architecture_decisions."""
        from . import tools
        return tools.get_architecture_decisions(
            self.db,
            module=arguments.get("module"),
            file_path=arguments.get("file_path"),
            status=arguments.get("status", "accepted"),
            include_superseded=False,
        )

    # =========================================================================
    # HANDLERS - Métriques & Risque
    # =========================================================================

    async def _handle_get_file_metrics(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_file_metrics."""
        from . import tools
        return tools.get_file_metrics(
            self.db,
            path=arguments["path"],
            include_per_function=arguments.get("include_per_function", False),
        )

    async def _handle_get_module_summary(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_module_summary."""
        from . import tools
        return tools.get_module_summary(
            self.db,
            module=arguments["module"],
            include_private=arguments.get("include_private", False),
        )

    async def _handle_get_risk_assessment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_risk_assessment."""
        from . import tools_v2
        return tools_v2.get_risk_assessment(
            self.db,
            file_paths=arguments["file_paths"],
            include_recommendations=arguments.get("include_recommendations", True),
        )

    # =========================================================================
    # HANDLERS - Recherche Sémantique
    # =========================================================================

    async def _handle_semantic_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour semantic_search."""
        from agentdb.semantic import create_search_engine

        engine = create_search_engine(self.db)
        search_type = arguments.get("search_type", "symbols")

        if search_type == "files":
            return engine.search_files(
                query=arguments["query"],
                top_k=arguments.get("top_k", 10),
                threshold=arguments.get("threshold", 0.3),
                module_filter=arguments.get("module"),
            )
        else:
            return engine.search_symbols(
                query=arguments["query"],
                top_k=arguments.get("top_k", 10),
                threshold=arguments.get("threshold", 0.3),
                kind_filter=arguments.get("kind"),
                module_filter=arguments.get("module"),
            )

    async def _handle_find_similar_code(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour find_similar_code."""
        from agentdb.semantic import create_search_engine

        engine = create_search_engine(self.db)
        similar = engine.find_similar_symbols(
            symbol_id=arguments["symbol_id"],
            top_k=arguments.get("top_k", 10),
            threshold=arguments.get("threshold", 0.5),
        )

        return {
            "symbol_id": arguments["symbol_id"],
            "similar": similar,
            "total": len(similar),
        }

    # =========================================================================
    # HANDLERS - Pattern Learning
    # =========================================================================

    async def _handle_learn_from_history(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour learn_from_history."""
        from agentdb.pattern_learner import create_pattern_learner

        learner = create_pattern_learner(self.db, Path.cwd())
        stats = learner.learn_from_git_history(
            days=arguments.get("days", 90),
            min_fixes=arguments.get("min_fixes", 2),
        )

        # Récupérer les patterns appris
        patterns = self.db.fetch_all(
            """
            SELECT name, category, confidence_score, occurrence_count
            FROM learned_patterns
            WHERE is_active = 1
            ORDER BY occurrence_count DESC
            LIMIT 10
            """
        )

        stats["patterns"] = [
            {
                "name": p["name"],
                "category": p["category"],
                "confidence": p["confidence_score"],
                "occurrences": p["occurrence_count"],
            }
            for p in patterns
        ]

        return stats

    async def _handle_detect_code_smells(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour detect_code_smells."""
        from agentdb.pattern_learner import create_pattern_learner

        learner = create_pattern_learner(self.db)
        smells = learner.detect_code_smells(
            file_path=arguments.get("file_path"),
            save_to_db=arguments.get("save_to_db", True),
        )

        by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for smell in smells:
            if smell.severity in by_severity:
                by_severity[smell.severity] += 1

        return {
            "file_path": arguments.get("file_path", "all"),
            "smells": [s.to_dict() for s in smells],
            "summary": {
                "total": len(smells),
                "by_severity": by_severity,
            },
        }

    async def _handle_get_suggestions(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_suggestions."""
        from agentdb.pattern_learner import create_pattern_learner

        learner = create_pattern_learner(self.db)
        return learner.get_suggestions(
            file_path=arguments["file_path"],
            include_patterns=arguments.get("include_patterns", True),
            include_smells=arguments.get("include_smells", True),
        )

    # =========================================================================
    # MCP PROTOCOL
    # =========================================================================

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Traite une requête JSON-RPC 2.0."""
        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        logger.debug(f"Handling request: method={method}, id={request_id}")

        try:
            if method == "initialize":
                result = await self._handle_initialize(params)
            elif method == "initialized":
                result = {}
            elif method == "tools/list":
                result = await self._handle_tools_list(params)
            elif method == "tools/call":
                result = await self._handle_tools_call(params)
            elif method == "shutdown":
                result = await self._handle_shutdown(params)
            else:
                return self._error_response(request_id, METHOD_NOT_FOUND, f"Unknown method: {method}")

            return self._success_response(request_id, result)

        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            return self._error_response(request_id, INTERNAL_ERROR, str(e))

    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
                "description": "AgentDB v6 Lean - Complements LSP with historical context, semantic search, and pattern learning"
            },
            "capabilities": {
                "tools": {"listChanged": False}
            }
        }

    async def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tools/list request."""
        return {"tools": TOOL_DEFINITIONS}

    async def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name not in self.tool_handlers:
            raise ValueError(f"Unknown tool: {tool_name}. Available: {list(self.tool_handlers.keys())}")

        handler = self.tool_handlers[tool_name]
        result = await handler(arguments)

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False)
                }
            ]
        }

    async def _handle_shutdown(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle shutdown request."""
        self.shutdown()
        return {}

    def _success_response(self, request_id: Any, result: Any) -> dict[str, Any]:
        """Build a success response."""
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _error_response(self, request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
        """Build an error response."""
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    # =========================================================================
    # STDIO TRANSPORT
    # =========================================================================

    async def run(self) -> None:
        """Lance le serveur en mode stdio."""
        logger.info(f"Starting AgentDB MCP server v{SERVER_VERSION} (stdio transport)...")

        self.initialize()

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

        logger.info("Server ready, waiting for requests...")

        try:
            while True:
                line = await reader.readline()
                if not line:
                    logger.info("EOF received, shutting down")
                    break

                line = line.decode("utf-8").strip()
                if not line:
                    continue

                logger.debug(f"Received: {line[:200]}...")

                try:
                    request = json.loads(line)
                    response = await self.handle_request(request)

                    if response:
                        response_str = json.dumps(response, ensure_ascii=False) + "\n"
                        writer.write(response_str.encode("utf-8"))
                        await writer.drain()

                except json.JSONDecodeError as e:
                    error_response = self._error_response(None, PARSE_ERROR, f"Invalid JSON: {e}")
                    writer.write((json.dumps(error_response) + "\n").encode("utf-8"))
                    await writer.drain()

        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
            raise
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Arrête proprement le serveur."""
        logger.info("Shutting down AgentDB server...")
        if self.db:
            try:
                self.db.close()
            except Exception as e:
                logger.error(f"Error closing database: {e}")
        self._initialized = False


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:
    """Point d'entrée du serveur MCP."""
    import argparse

    parser = argparse.ArgumentParser(description="AgentDB MCP Server v6 Lean")
    parser.add_argument("--db", "-d", help="Path to SQLite database", default=None)
    parser.add_argument("--config", "-c", help="Path to YAML config file", default=None)
    parser.add_argument(
        "--log-level", "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO"
    )
    args = parser.parse_args()

    logging.getLogger("agentdb").setLevel(args.log_level)

    server = AgentDBServer(db_path=args.db, config_path=args.config)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
