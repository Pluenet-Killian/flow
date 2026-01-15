"""
Hybrid LSP + AgentDB Layer - Architecture de nouvelle génération.

Ce module combine la puissance du LSP natif de Claude Code avec
l'enrichissement contextuel d'AgentDB pour offrir une analyse
de code plus complète et plus rapide.

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                    CLAUDE CODE LSP                       │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
    │  │goToDefinition│  │findReferences│  │ incomingCalls  │  │
    │  │outgoingCalls │  │    hover    │  │workspaceSymbol │  │
    │  └──────┬──────┘  └──────┬──────┘  └─────────┬───────┘  │
    └─────────┼────────────────┼───────────────────┼──────────┘
              │                │                   │
              ▼                ▼                   ▼
    ┌─────────────────────────────────────────────────────────┐
    │              HYBRID LAYER (ce module)                    │
    │                                                          │
    │  ┌────────────────┐  ┌────────────────┐                 │
    │  │ LSP Results    │──│ AgentDB Enrich │                 │
    │  │ (fast, precise)│  │ (context, hist)│                 │
    │  └────────────────┘  └────────────────┘                 │
    │                                                          │
    │  Enrichissements:                                        │
    │  - error_history (mémoire des bugs)                     │
    │  - criticality_score (fichiers critiques)               │
    │  - git_activity (commits récents)                       │
    │  - patterns (règles métier)                             │
    │  - architecture_decisions (ADRs)                        │
    └─────────────────────────────────────────────────────────┘

Usage:
    from agentdb.hybrid_lsp import HybridAnalyzer

    analyzer = HybridAnalyzer(db)

    # Références enrichies
    refs = await analyzer.smart_references("src/main.py", 10, 5)

    # Analyse d'impact v2
    impact = await analyzer.impact_analysis_v2("src/main.py", ["def foo"])
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol
from datetime import datetime, timedelta

logger = logging.getLogger("agentdb.hybrid_lsp")


# =============================================================================
# PROTOCOLS & DATA CLASSES
# =============================================================================

class DatabaseProtocol(Protocol):
    """Protocol pour la connexion à la base de données."""
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]: ...
    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]: ...


@dataclass
class LSPLocation:
    """Représente une localisation dans le code."""
    file_path: str
    line: int
    character: int

    def to_dict(self) -> dict:
        return {
            "file": self.file_path,
            "line": self.line,
            "character": self.character,
        }


@dataclass
class LSPReference:
    """Référence LSP avec enrichissement AgentDB."""
    location: LSPLocation
    symbol_name: Optional[str] = None
    kind: Optional[str] = None
    # Enrichissements AgentDB
    is_critical: bool = False
    error_count: int = 0
    git_activity: int = 0
    criticality_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            **self.location.to_dict(),
            "symbol": self.symbol_name,
            "kind": self.kind,
            "is_critical": self.is_critical,
            "error_count": self.error_count,
            "git_activity": self.git_activity,
            "criticality_score": self.criticality_score,
        }


@dataclass
class CallHierarchyItem:
    """Item de la hiérarchie d'appels avec enrichissement."""
    name: str
    kind: str
    file_path: str
    line: int
    # Enrichissements
    is_critical: bool = False
    error_history: list[dict] = field(default_factory=list)
    patterns_violated: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "file": self.file_path,
            "line": self.line,
            "is_critical": self.is_critical,
            "error_history": self.error_history,
            "patterns_violated": self.patterns_violated,
        }


@dataclass
class ImpactResult:
    """Résultat d'analyse d'impact enrichi."""
    file_path: str
    direct_references: list[LSPReference]
    call_hierarchy: list[CallHierarchyItem]
    historical_bugs: list[dict]
    similar_changes: list[dict]
    risk_score: float
    risk_factors: list[str]

    def to_dict(self) -> dict:
        return {
            "file": self.file_path,
            "direct_references": [r.to_dict() for r in self.direct_references],
            "call_hierarchy": [c.to_dict() for c in self.call_hierarchy],
            "historical_bugs": self.historical_bugs,
            "similar_changes": self.similar_changes,
            "risk_score": self.risk_score,
            "risk_factors": self.risk_factors,
        }


# =============================================================================
# LSP CLIENT INTERFACE
# =============================================================================

class LSPClient:
    """
    Client pour interagir avec le LSP de Claude Code.

    Note: Dans un contexte MCP, le LSP est accessible via l'outil LSP
    de Claude Code. Ce client simule l'interface pour les tests
    et peut être remplacé par l'appel réel au LSP.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._lsp_available = self._check_lsp_available()

    def _check_lsp_available(self) -> bool:
        """Vérifie si le LSP est disponible."""
        # Le LSP est disponible si nous sommes dans un contexte Claude Code
        # Pour l'instant, on retourne True par défaut
        return True

    @property
    def available(self) -> bool:
        return self._lsp_available

    def find_references(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> list[LSPLocation]:
        """
        Trouve toutes les références à un symbole.

        Equivalent LSP: findReferences
        """
        if not self._lsp_available:
            return []

        # Note: Dans le contexte MCP réel, ceci appellera l'outil LSP
        # Pour l'instant, retourne une liste vide (sera enrichi par AgentDB)
        return self._call_lsp("findReferences", file_path, line, character)

    def incoming_calls(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> list[CallHierarchyItem]:
        """
        Trouve tous les appelants d'une fonction.

        Equivalent LSP: prepareCallHierarchy + incomingCalls
        """
        if not self._lsp_available:
            return []

        return self._call_lsp("incomingCalls", file_path, line, character)

    def outgoing_calls(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> list[CallHierarchyItem]:
        """
        Trouve tous les appelés d'une fonction.

        Equivalent LSP: prepareCallHierarchy + outgoingCalls
        """
        if not self._lsp_available:
            return []

        return self._call_lsp("outgoingCalls", file_path, line, character)

    def go_to_definition(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> Optional[LSPLocation]:
        """
        Trouve la définition d'un symbole.

        Equivalent LSP: goToDefinition
        """
        if not self._lsp_available:
            return None

        result = self._call_lsp("goToDefinition", file_path, line, character)
        return result[0] if result else None

    def workspace_symbol(self, query: str) -> list[dict]:
        """
        Recherche des symboles dans le workspace.

        Equivalent LSP: workspaceSymbol
        """
        if not self._lsp_available:
            return []

        # Pour workspaceSymbol, on utilise un format différent
        return self._call_lsp_workspace_symbol(query)

    def hover(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> Optional[dict]:
        """
        Récupère les informations de hover (documentation, type).

        Equivalent LSP: hover
        """
        if not self._lsp_available:
            return None

        return self._call_lsp("hover", file_path, line, character)

    def _call_lsp(
        self,
        operation: str,
        file_path: str,
        line: int,
        character: int
    ) -> list:
        """
        Appelle le LSP via l'interface Claude Code.

        Note: Cette méthode sera appelée dans le contexte MCP
        où l'outil LSP est disponible. Pour l'instant, elle
        retourne une liste vide comme fallback.
        """
        # Dans le contexte réel, ceci utilisera l'outil LSP
        # Exemple de ce que ça ferait:
        # result = await mcp_call("LSP", {
        #     "operation": operation,
        #     "filePath": file_path,
        #     "line": line,
        #     "character": character
        # })
        logger.debug(f"LSP call: {operation} on {file_path}:{line}:{character}")
        return []

    def _call_lsp_workspace_symbol(self, query: str) -> list[dict]:
        """Appelle workspaceSymbol."""
        logger.debug(f"LSP workspaceSymbol: {query}")
        return []


# =============================================================================
# AGENTDB ENRICHER
# =============================================================================

class AgentDBEnricher:
    """
    Enrichit les résultats LSP avec le contexte AgentDB.

    Ajoute:
    - Historique des erreurs
    - Score de criticité
    - Activité Git
    - Patterns applicables
    - Décisions architecturales
    """

    def __init__(self, db: DatabaseProtocol):
        self.db = db
        self._cache: dict[str, dict] = {}

    def enrich_reference(self, ref: LSPReference) -> LSPReference:
        """Enrichit une référence avec le contexte AgentDB."""
        file_info = self._get_file_info(ref.location.file_path)

        if file_info:
            ref.is_critical = bool(file_info.get("is_critical", False))
            ref.git_activity = file_info.get("commits_30d", 0) or 0
            ref.criticality_score = self._calculate_criticality(file_info)

            # Compter les erreurs récentes
            ref.error_count = self._count_recent_errors(ref.location.file_path)

        return ref

    def enrich_call_item(self, item: CallHierarchyItem) -> CallHierarchyItem:
        """Enrichit un item de hiérarchie d'appels."""
        file_info = self._get_file_info(item.file_path)

        if file_info:
            item.is_critical = bool(file_info.get("is_critical", False))

            # Récupérer l'historique des erreurs
            item.error_history = self._get_error_history(item.file_path, limit=3)

            # Vérifier les patterns violés
            item.patterns_violated = self._check_patterns(item.file_path, item.name)

        return item

    def get_historical_bugs(
        self,
        file_path: str,
        days: int = 365
    ) -> list[dict]:
        """Récupère l'historique des bugs pour un fichier."""
        return self._get_error_history(file_path, days=days, limit=20)

    def find_similar_changes(
        self,
        file_path: str,
        changes: list[str]
    ) -> list[dict]:
        """
        Trouve des changements similaires dans l'historique.

        Utilise l'historique des erreurs et patterns pour identifier
        des modifications similaires qui ont causé des problèmes.
        """
        # Récupérer les erreurs passées avec leur contexte
        similar = []

        try:
            # Chercher des patterns dans error_history qui matchent
            rows = self.db.fetch_all(
                """
                SELECT
                    error_type, title, resolution, prevention,
                    root_cause, code_context
                FROM error_history
                WHERE file_path LIKE ? OR file_path = ?
                AND resolution IS NOT NULL
                ORDER BY discovered_at DESC
                LIMIT 10
                """,
                (f"%{Path(file_path).name}", file_path),
            )

            for row in rows:
                similar.append({
                    "type": row.get("error_type"),
                    "title": row.get("title"),
                    "resolution": row.get("resolution"),
                    "prevention": row.get("prevention"),
                    "root_cause": row.get("root_cause"),
                })
        except Exception as e:
            logger.warning(f"Error finding similar changes: {e}")

        return similar

    def calculate_risk_score(
        self,
        file_path: str,
        references_count: int,
        critical_count: int,
        error_count: int
    ) -> tuple[float, list[str]]:
        """
        Calcule un score de risque pour une modification.

        Returns:
            Tuple (score 0-100, liste des facteurs de risque)
        """
        score = 0.0
        factors = []

        file_info = self._get_file_info(file_path)

        # Facteur 1: Fichier critique
        if file_info and file_info.get("is_critical"):
            score += 25
            factors.append("Critical file")

        # Facteur 2: Beaucoup de références
        if references_count > 20:
            score += 20
            factors.append(f"High reference count ({references_count})")
        elif references_count > 10:
            score += 10
            factors.append(f"Moderate reference count ({references_count})")

        # Facteur 3: Références critiques
        if critical_count > 0:
            score += min(critical_count * 10, 25)
            factors.append(f"References from {critical_count} critical files")

        # Facteur 4: Historique d'erreurs
        if error_count > 5:
            score += 20
            factors.append(f"High error history ({error_count})")
        elif error_count > 0:
            score += 10
            factors.append(f"Has error history ({error_count})")

        # Facteur 5: Complexité
        if file_info:
            complexity = file_info.get("complexity_max", 0) or 0
            if complexity > 20:
                score += 15
                factors.append(f"High complexity ({complexity})")
            elif complexity > 10:
                score += 5
                factors.append(f"Moderate complexity ({complexity})")

        # Facteur 6: Activité récente (fichier instable)
        if file_info:
            commits = file_info.get("commits_30d", 0) or 0
            if commits > 10:
                score += 10
                factors.append(f"High churn ({commits} commits/30d)")

        return min(score, 100), factors

    def _get_file_info(self, file_path: str) -> Optional[dict]:
        """Récupère les informations d'un fichier (avec cache)."""
        if file_path in self._cache:
            return self._cache[file_path]

        try:
            row = self.db.fetch_one(
                """
                SELECT
                    id, path, module, is_critical, security_sensitive,
                    lines_code, complexity_max, complexity_avg,
                    commits_30d, commits_90d, documentation_score
                FROM files
                WHERE path = ? OR path LIKE ?
                """,
                (file_path, f"%{file_path}"),
            )

            if row:
                self._cache[file_path] = dict(row)
                return self._cache[file_path]
        except Exception as e:
            logger.warning(f"Error getting file info: {e}")

        return None

    def _count_recent_errors(self, file_path: str, days: int = 90) -> int:
        """Compte les erreurs récentes pour un fichier."""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            row = self.db.fetch_one(
                """
                SELECT COUNT(*) as cnt
                FROM error_history
                WHERE (file_path = ? OR file_path LIKE ?)
                AND discovered_at >= ?
                """,
                (file_path, f"%{file_path}", cutoff),
            )
            return row.get("cnt", 0) if row else 0
        except Exception:
            return 0

    def _get_error_history(
        self,
        file_path: str,
        days: int = 365,
        limit: int = 10
    ) -> list[dict]:
        """Récupère l'historique des erreurs."""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            rows = self.db.fetch_all(
                """
                SELECT
                    error_type, severity, title,
                    resolved_at, resolution, prevention
                FROM error_history
                WHERE (file_path = ? OR file_path LIKE ?)
                AND discovered_at >= ?
                ORDER BY discovered_at DESC
                LIMIT ?
                """,
                (file_path, f"%{file_path}", cutoff, limit),
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _check_patterns(
        self,
        file_path: str,
        symbol_name: str
    ) -> list[str]:
        """Vérifie les patterns potentiellement violés."""
        violated = []

        try:
            # Récupérer les patterns applicables
            rows = self.db.fetch_all(
                """
                SELECT name, title, file_pattern
                FROM patterns
                WHERE is_active = 1
                AND (file_pattern IS NULL OR ? GLOB file_pattern)
                """,
                (file_path,),
            )

            # Pour l'instant, on retourne juste les noms des patterns
            # Une vraie implémentation vérifierait le code
            for row in rows:
                if row.get("name"):
                    violated.append(row["name"])
        except Exception:
            pass

        return violated[:3]  # Limiter à 3 patterns

    def _calculate_criticality(self, file_info: dict) -> float:
        """Calcule un score de criticité (0-1)."""
        score = 0.0

        if file_info.get("is_critical"):
            score += 0.4

        if file_info.get("security_sensitive"):
            score += 0.3

        commits = file_info.get("commits_30d", 0) or 0
        if commits > 5:
            score += 0.2

        complexity = file_info.get("complexity_max", 0) or 0
        if complexity > 15:
            score += 0.1

        return min(score, 1.0)


# =============================================================================
# HYBRID ANALYZER
# =============================================================================

class HybridAnalyzer:
    """
    Analyseur hybride combinant LSP + AgentDB.

    Utilise le LSP pour les requêtes rapides et précises,
    puis enrichit avec le contexte AgentDB.
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        project_root: Optional[Path] = None
    ):
        self.db = db
        self.project_root = project_root or Path.cwd()
        self.lsp = LSPClient(self.project_root)
        self.enricher = AgentDBEnricher(db)

    def smart_references(
        self,
        file_path: str,
        line: int,
        character: int,
        include_indirect: bool = True
    ) -> dict[str, Any]:
        """
        Trouve les références à un symbole avec enrichissement complet.

        Combine:
        - LSP findReferences (rapide, précis)
        - AgentDB enrichissement (contexte, historique)

        Returns:
            Dict avec references triées par criticité, summary, risk_assessment
        """
        # 1. Appeler LSP pour les références
        lsp_refs = self.lsp.find_references(file_path, line, character)

        # 2. Fallback sur AgentDB si LSP non disponible ou vide
        if not lsp_refs:
            lsp_refs = self._fallback_references_from_agentdb(
                file_path, line, character
            )

        # 3. Convertir et enrichir
        references: list[LSPReference] = []
        for loc in lsp_refs:
            ref = LSPReference(location=loc)
            ref = self.enricher.enrich_reference(ref)
            references.append(ref)

        # 4. Trier par criticité (plus critiques en premier)
        references.sort(key=lambda r: r.criticality_score, reverse=True)

        # 5. Calculer les statistiques
        critical_count = sum(1 for r in references if r.is_critical)
        error_total = sum(r.error_count for r in references)
        files_affected = list(set(r.location.file_path for r in references))

        return {
            "query": {
                "file": file_path,
                "line": line,
                "character": character,
            },
            "references": [r.to_dict() for r in references],
            "summary": {
                "total_references": len(references),
                "critical_references": critical_count,
                "files_affected": len(files_affected),
                "total_historical_errors": error_total,
            },
            "files_affected": files_affected,
        }

    def smart_callers(
        self,
        file_path: str,
        line: int,
        character: int,
        max_depth: int = 3
    ) -> dict[str, Any]:
        """
        Trouve les appelants d'une fonction avec enrichissement.

        Combine:
        - LSP incomingCalls (rapide, précis)
        - AgentDB enrichissement (patterns, erreurs)
        """
        # 1. Appeler LSP
        lsp_callers = self.lsp.incoming_calls(file_path, line, character)

        # 2. Fallback sur AgentDB
        if not lsp_callers:
            lsp_callers = self._fallback_callers_from_agentdb(
                file_path, line, character
            )

        # 3. Enrichir
        callers: list[CallHierarchyItem] = []
        for item in lsp_callers:
            item = self.enricher.enrich_call_item(item)
            callers.append(item)

        # 4. Organiser par criticité
        critical_callers = [c for c in callers if c.is_critical]
        normal_callers = [c for c in callers if not c.is_critical]

        return {
            "query": {
                "file": file_path,
                "line": line,
                "character": character,
            },
            "callers": {
                "critical": [c.to_dict() for c in critical_callers],
                "normal": [c.to_dict() for c in normal_callers],
            },
            "summary": {
                "total_callers": len(callers),
                "critical_callers": len(critical_callers),
                "with_error_history": sum(
                    1 for c in callers if c.error_history
                ),
            },
        }

    def impact_analysis_v2(
        self,
        file_path: str,
        changes: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """
        Analyse d'impact moderne combinant LSP + historique.

        Returns:
            Dict avec references, call_hierarchy, historical_bugs,
            similar_changes, risk_score, risk_factors
        """
        changes = changes or []

        # 1. Trouver les symboles du fichier
        symbols = self._get_file_symbols(file_path)

        # 2. Pour chaque symbole, collecter les références
        all_references: list[LSPReference] = []
        all_callers: list[CallHierarchyItem] = []

        for sym in symbols[:10]:  # Limiter pour performance
            line = sym.get("line_start", 1)

            # Références
            refs = self.lsp.find_references(file_path, line, 1)
            for loc in refs:
                ref = LSPReference(location=loc, symbol_name=sym.get("name"))
                ref = self.enricher.enrich_reference(ref)
                all_references.append(ref)

            # Appelants (si c'est une fonction)
            if sym.get("kind") in ("function", "method"):
                callers = self.lsp.incoming_calls(file_path, line, 1)
                for item in callers:
                    item = self.enricher.enrich_call_item(item)
                    all_callers.append(item)

        # 3. Historique des bugs
        historical_bugs = self.enricher.get_historical_bugs(file_path)

        # 4. Changements similaires
        similar_changes = self.enricher.find_similar_changes(file_path, changes)

        # 5. Calculer le risque
        critical_count = sum(1 for r in all_references if r.is_critical)
        error_count = len(historical_bugs)

        risk_score, risk_factors = self.enricher.calculate_risk_score(
            file_path,
            len(all_references),
            critical_count,
            error_count
        )

        # Construire le résultat
        result = ImpactResult(
            file_path=file_path,
            direct_references=all_references,
            call_hierarchy=all_callers,
            historical_bugs=historical_bugs,
            similar_changes=similar_changes,
            risk_score=risk_score,
            risk_factors=risk_factors,
        )

        return result.to_dict()

    def smart_search(
        self,
        query: str,
        kind: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = 50
    ) -> dict[str, Any]:
        """
        Recherche hybride combinant LSP workspaceSymbol + AgentDB.

        Le LSP est utilisé pour la recherche rapide, AgentDB
        pour le filtrage avancé et l'enrichissement.
        """
        # 1. Essayer LSP d'abord
        lsp_results = self.lsp.workspace_symbol(query)

        # 2. Si LSP vide ou filtres avancés, utiliser AgentDB
        if not lsp_results or kind or module:
            return self._search_from_agentdb(query, kind, module, limit)

        # 3. Enrichir les résultats LSP
        enriched = []
        for result in lsp_results[:limit]:
            file_path = result.get("file", "")
            file_info = self.enricher._get_file_info(file_path)

            enriched.append({
                **result,
                "is_critical": file_info.get("is_critical", False) if file_info else False,
                "module": file_info.get("module") if file_info else None,
            })

        return {
            "query": query,
            "results": enriched,
            "total": len(enriched),
            "source": "hybrid",
        }

    # =========================================================================
    # FALLBACK METHODS (quand LSP non disponible)
    # =========================================================================

    def _fallback_references_from_agentdb(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> list[LSPLocation]:
        """Fallback: utilise AgentDB pour trouver les références."""
        references = []

        try:
            # Trouver le symbole à cette position
            symbol = self.db.fetch_one(
                """
                SELECT s.id, s.name
                FROM symbols s
                JOIN files f ON s.file_id = f.id
                WHERE f.path LIKE ?
                AND s.line_start <= ? AND s.line_end >= ?
                ORDER BY s.line_start DESC
                LIMIT 1
                """,
                (f"%{file_path}", line, line),
            )

            if symbol:
                # Trouver les appelants
                rows = self.db.fetch_all(
                    """
                    SELECT f.path, r.location_line as line
                    FROM relations r
                    JOIN symbols s ON r.source_id = s.id
                    JOIN files f ON s.file_id = f.id
                    WHERE r.target_id = ?
                    AND r.relation_type = 'calls'
                    """,
                    (symbol["id"],),
                )

                for row in rows:
                    references.append(LSPLocation(
                        file_path=row["path"],
                        line=row.get("line", 1),
                        character=1,
                    ))
        except Exception as e:
            logger.warning(f"Fallback references error: {e}")

        return references

    def _fallback_callers_from_agentdb(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> list[CallHierarchyItem]:
        """Fallback: utilise AgentDB pour trouver les appelants."""
        callers = []

        try:
            # Trouver le symbole
            symbol = self.db.fetch_one(
                """
                SELECT s.id, s.name, s.kind
                FROM symbols s
                JOIN files f ON s.file_id = f.id
                WHERE f.path LIKE ?
                AND s.line_start <= ? AND s.line_end >= ?
                ORDER BY s.line_start DESC
                LIMIT 1
                """,
                (f"%{file_path}", line, line),
            )

            if symbol:
                rows = self.db.fetch_all(
                    """
                    SELECT s.name, s.kind, f.path, r.location_line as line
                    FROM relations r
                    JOIN symbols s ON r.source_id = s.id
                    JOIN files f ON s.file_id = f.id
                    WHERE r.target_id = ?
                    AND r.relation_type = 'calls'
                    LIMIT 50
                    """,
                    (symbol["id"],),
                )

                for row in rows:
                    callers.append(CallHierarchyItem(
                        name=row["name"],
                        kind=row.get("kind", "function"),
                        file_path=row["path"],
                        line=row.get("line", 1),
                    ))
        except Exception as e:
            logger.warning(f"Fallback callers error: {e}")

        return callers

    def _get_file_symbols(self, file_path: str) -> list[dict]:
        """Récupère les symboles d'un fichier."""
        try:
            rows = self.db.fetch_all(
                """
                SELECT s.name, s.kind, s.line_start, s.line_end
                FROM symbols s
                JOIN files f ON s.file_id = f.id
                WHERE f.path LIKE ?
                ORDER BY s.line_start
                """,
                (f"%{file_path}",),
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _search_from_agentdb(
        self,
        query: str,
        kind: Optional[str],
        module: Optional[str],
        limit: int
    ) -> dict[str, Any]:
        """Recherche via AgentDB uniquement."""
        sql_pattern = query.replace("*", "%").replace("?", "_")

        sql = """
            SELECT s.name, s.kind, f.path as file, s.signature, s.line_start as line
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.name LIKE ?
        """
        params: list[Any] = [sql_pattern]

        if kind:
            sql += " AND s.kind = ?"
            params.append(kind)

        if module:
            sql += " AND f.module = ?"
            params.append(module)

        sql += " ORDER BY s.name LIMIT ?"
        params.append(limit)

        try:
            rows = self.db.fetch_all(sql, tuple(params))
            results = [dict(r) for r in rows]

            return {
                "query": query,
                "results": results,
                "total": len(results),
                "source": "agentdb",
            }
        except Exception as e:
            logger.error(f"AgentDB search error: {e}")
            return {"query": query, "results": [], "total": 0, "source": "error"}


# =============================================================================
# FACTORY & EXPORTS
# =============================================================================

def create_hybrid_analyzer(
    db: DatabaseProtocol,
    project_root: Optional[Path] = None
) -> HybridAnalyzer:
    """Factory pour créer un analyseur hybride."""
    return HybridAnalyzer(db, project_root)


__all__ = [
    "HybridAnalyzer",
    "LSPClient",
    "AgentDBEnricher",
    "LSPLocation",
    "LSPReference",
    "CallHierarchyItem",
    "ImpactResult",
    "create_hybrid_analyzer",
]
