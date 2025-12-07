"""
AgentDB MCP Server - Serveur principal.

Ce module implémente le serveur MCP qui expose AgentDB aux agents Claude.

Architecture :
- Transport : stdio (JSON-RPC 2.0)
- Protocole : MCP (Model Context Protocol)
- Backend : SQLite via le module agentdb

Le serveur gère :
- L'initialisation de la connexion DB
- L'enregistrement des outils
- Le dispatch des requêtes
- La gestion des erreurs

Usage:
    # Direct
    python -m mcp.agentdb.server

    # Programmatique
    server = AgentDBServer()
    server.run()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

# MCP SDK imports (à installer: pip install mcp)
# from mcp import Server, Tool
# from mcp.types import TextContent

# Import local d'AgentDB
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentdb import Database
from agentdb.queries import GraphQueries, HistoryQueries, KnowledgeQueries, FileContextQuery

from . import tools

# Configuration du logging
logging.basicConfig(
    level=os.environ.get("AGENTDB_LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("agentdb.mcp")


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "get_file_context",
        "description": """Récupère le contexte complet d'un fichier : métadonnées, symboles,
dépendances, historique d'erreurs, métriques, et patterns applicables.
C'est l'outil le plus utilisé - il donne une vue 360° d'un fichier.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Chemin du fichier relatif à la racine du projet"
                },
                "include_symbols": {
                    "type": "boolean",
                    "default": True,
                    "description": "Inclure la liste des symboles"
                },
                "include_dependencies": {
                    "type": "boolean",
                    "default": True,
                    "description": "Inclure les dépendances (includes, appelants)"
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
    {
        "name": "get_symbol_callers",
        "description": """Trouve tous les symboles qui appellent le symbole donné,
avec traversée récursive jusqu'à une profondeur configurable.
Essentiel pour l'analyse d'impact.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol_name": {
                    "type": "string",
                    "description": "Nom du symbole (fonction, variable, etc.)"
                },
                "file_path": {
                    "type": "string",
                    "description": "Fichier du symbole (pour désambiguïser)"
                },
                "max_depth": {
                    "type": "integer",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Profondeur maximale de traversée"
                },
                "include_indirect": {
                    "type": "boolean",
                    "default": True,
                    "description": "Inclure les appels indirects (via pointeurs)"
                }
            },
            "required": ["symbol_name"]
        }
    },
    {
        "name": "get_symbol_callees",
        "description": """Trouve tous les symboles appelés par le symbole donné.
Utile pour comprendre les dépendances d'une fonction.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol_name": {
                    "type": "string",
                    "description": "Nom du symbole"
                },
                "file_path": {
                    "type": "string",
                    "description": "Fichier du symbole (optionnel)"
                },
                "max_depth": {
                    "type": "integer",
                    "default": 2,
                    "description": "Profondeur de traversée"
                }
            },
            "required": ["symbol_name"]
        }
    },
    {
        "name": "get_file_impact",
        "description": """Calcule l'impact complet de la modification d'un fichier.
Combine : fichiers qui incluent + fichiers avec symboles appelants.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Chemin du fichier"
                },
                "include_transitive": {
                    "type": "boolean",
                    "default": True,
                    "description": "Inclure les impacts transitifs"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "get_error_history",
        "description": """Récupère l'historique des erreurs/bugs pour un fichier,
un symbole, ou un module entier.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Filtrer par fichier"
                },
                "symbol_name": {
                    "type": "string",
                    "description": "Filtrer par symbole"
                },
                "module": {
                    "type": "string",
                    "description": "Filtrer par module"
                },
                "error_type": {
                    "type": "string",
                    "description": "Filtrer par type d'erreur"
                },
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low"],
                    "description": "Filtrer par sévérité minimum"
                },
                "days": {
                    "type": "integer",
                    "default": 180,
                    "description": "Période en jours"
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Nombre max de résultats"
                }
            }
        }
    },
    {
        "name": "get_patterns",
        "description": """Récupère les patterns de code applicables à un fichier ou module.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Fichier pour lequel récupérer les patterns"
                },
                "module": {
                    "type": "string",
                    "description": "Module pour lequel récupérer les patterns"
                },
                "category": {
                    "type": "string",
                    "description": "Catégorie de patterns"
                }
            }
        }
    },
    {
        "name": "get_architecture_decisions",
        "description": """Récupère les décisions architecturales (ADR) applicables.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module": {
                    "type": "string",
                    "description": "Filtrer par module"
                },
                "file_path": {
                    "type": "string",
                    "description": "Filtrer par fichier"
                },
                "status": {
                    "type": "string",
                    "enum": ["accepted", "proposed", "deprecated"],
                    "default": "accepted"
                }
            }
        }
    },
    {
        "name": "search_symbols",
        "description": """Recherche des symboles par nom, type, ou pattern.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pattern de recherche (supporte * et ?)"
                },
                "kind": {
                    "type": "string",
                    "enum": ["function", "struct", "class", "enum", "macro", "variable"],
                    "description": "Type de symbole"
                },
                "module": {
                    "type": "string",
                    "description": "Filtrer par module"
                },
                "limit": {
                    "type": "integer",
                    "default": 50
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_file_metrics",
        "description": """Récupère les métriques détaillées d'un fichier.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Chemin du fichier"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "get_module_summary",
        "description": """Récupère un résumé complet d'un module (ensemble de fichiers).""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module": {
                    "type": "string",
                    "description": "Nom du module"
                }
            },
            "required": ["module"]
        }
    }
]


# =============================================================================
# MCP SERVER
# =============================================================================

class AgentDBServer:
    """
    Serveur MCP pour AgentDB.

    Gère la communication avec les agents Claude via stdio.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialise le serveur.

        Args:
            db_path: Chemin vers la base SQLite (défaut: env AGENTDB_PATH)
        """
        self.db_path = db_path or os.environ.get(
            "AGENTDB_PATH",
            ".claude/agentdb/db.sqlite"
        )
        self.db: Optional[Database] = None
        self.graph_queries: Optional[GraphQueries] = None
        self.history_queries: Optional[HistoryQueries] = None
        self.knowledge_queries: Optional[KnowledgeQueries] = None
        self.file_context_query: Optional[FileContextQuery] = None

        # Mapping des noms d'outils vers les fonctions
        self.tool_handlers: dict[str, Callable] = {}

    def initialize(self) -> None:
        """
        Initialise la connexion DB et les handlers.
        """
        # TODO: Implémenter
        # 1. Connecter à la DB
        # 2. Initialiser les query objects
        # 3. Enregistrer les handlers
        logger.info(f"Initializing AgentDB server with DB: {self.db_path}")
        pass

    def _register_handlers(self) -> None:
        """
        Enregistre les handlers pour chaque outil.
        """
        self.tool_handlers = {
            "get_file_context": self._handle_get_file_context,
            "get_symbol_callers": self._handle_get_symbol_callers,
            "get_symbol_callees": self._handle_get_symbol_callees,
            "get_file_impact": self._handle_get_file_impact,
            "get_error_history": self._handle_get_error_history,
            "get_patterns": self._handle_get_patterns,
            "get_architecture_decisions": self._handle_get_architecture_decisions,
            "search_symbols": self._handle_search_symbols,
            "get_file_metrics": self._handle_get_file_metrics,
            "get_module_summary": self._handle_get_module_summary,
        }

    # -------------------------------------------------------------------------
    # TOOL HANDLERS
    # -------------------------------------------------------------------------

    async def _handle_get_file_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_file_context."""
        # TODO: Implémenter avec tools.get_file_context
        pass

    async def _handle_get_symbol_callers(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_symbol_callers."""
        # TODO: Implémenter avec tools.get_symbol_callers
        pass

    async def _handle_get_symbol_callees(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_symbol_callees."""
        # TODO: Implémenter avec tools.get_symbol_callees
        pass

    async def _handle_get_file_impact(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_file_impact."""
        # TODO: Implémenter avec tools.get_file_impact
        pass

    async def _handle_get_error_history(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_error_history."""
        # TODO: Implémenter avec tools.get_error_history
        pass

    async def _handle_get_patterns(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_patterns."""
        # TODO: Implémenter avec tools.get_patterns
        pass

    async def _handle_get_architecture_decisions(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_architecture_decisions."""
        # TODO: Implémenter avec tools.get_architecture_decisions
        pass

    async def _handle_search_symbols(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour search_symbols."""
        # TODO: Implémenter avec tools.search_symbols
        pass

    async def _handle_get_file_metrics(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_file_metrics."""
        # TODO: Implémenter avec tools.get_file_metrics
        pass

    async def _handle_get_module_summary(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handler pour get_module_summary."""
        # TODO: Implémenter avec tools.get_module_summary
        pass

    # -------------------------------------------------------------------------
    # MCP PROTOCOL
    # -------------------------------------------------------------------------

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Traite une requête JSON-RPC.

        Args:
            request: Requête JSON-RPC

        Returns:
            Réponse JSON-RPC
        """
        # TODO: Implémenter le dispatch JSON-RPC
        # - initialize: retourner les capabilities
        # - tools/list: retourner TOOL_DEFINITIONS
        # - tools/call: dispatch vers le handler approprié
        pass

    async def run(self) -> None:
        """
        Lance le serveur en mode stdio.
        """
        # TODO: Implémenter la boucle de lecture/écriture stdio
        # 1. Initialiser
        # 2. Lire les requêtes de stdin
        # 3. Traiter et écrire les réponses sur stdout
        logger.info("Starting AgentDB MCP server...")
        self.initialize()

        # Boucle principale
        try:
            while True:
                # TODO: Lire une ligne JSON de stdin
                # TODO: Parser et traiter
                # TODO: Écrire la réponse sur stdout
                pass
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise

    def shutdown(self) -> None:
        """
        Arrête proprement le serveur.
        """
        # TODO: Fermer la connexion DB
        if self.db:
            self.db.close()
        logger.info("AgentDB server shut down")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:
    """
    Point d'entrée du serveur MCP.
    """
    server = AgentDBServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
