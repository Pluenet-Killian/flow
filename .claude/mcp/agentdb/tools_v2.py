"""
AgentDB MCP Tools v2 - Outils hybrides LSP + AgentDB.

Ce module ajoute de nouveaux outils qui combinent la puissance du LSP
natif de Claude Code avec l'enrichissement contextuel d'AgentDB.

Nouveaux outils hybrides:
- smart_references: Références enrichies avec contexte historique
- smart_callers: Appelants avec patterns et erreurs
- impact_analysis_v2: Analyse d'impact moderne
- smart_search: Recherche hybride LSP + AgentDB

Ces outils sont conçus pour être utilisés en priorité quand le LSP
est disponible, avec fallback automatique sur AgentDB seul.

Migration recommandée:
- get_symbol_callers  → smart_callers
- get_symbol_callees  → (utiliser LSP outgoingCalls directement)
- search_symbols      → smart_search
- get_file_impact     → impact_analysis_v2
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("agentdb.mcp.tools_v2")


# =============================================================================
# OUTIL HYBRIDE 1: SMART_REFERENCES
# =============================================================================

def smart_references(
    db,
    file_path: str,
    line: int,
    character: int,
    include_indirect: bool = True,
    sort_by: str = "criticality"  # criticality, file, line
) -> dict[str, Any]:
    """
    Trouve les références à un symbole avec enrichissement complet.

    Combine LSP findReferences + enrichissement AgentDB pour fournir:
    - Liste des références triées par criticité
    - Historique des erreurs pour chaque fichier référençant
    - Score de criticité calculé
    - Activité Git récente

    Avantages vs get_symbol_callers:
    - Plus rapide (LSP est optimisé)
    - Plus précis (AST complet)
    - Contexte enrichi (métriques AgentDB)

    Args:
        db: Connexion à la base
        file_path: Chemin du fichier source
        line: Numéro de ligne (1-based)
        character: Position dans la ligne (1-based)
        include_indirect: Inclure les références indirectes
        sort_by: Tri des résultats (criticality, file, line)

    Returns:
        Dict avec query, references[], summary, files_affected
    """
    from agentdb.hybrid_lsp import create_hybrid_analyzer

    try:
        analyzer = create_hybrid_analyzer(db)
        result = analyzer.smart_references(
            file_path, line, character, include_indirect
        )

        # Appliquer le tri demandé
        refs = result.get("references", [])
        if sort_by == "file":
            refs.sort(key=lambda r: r.get("file", ""))
        elif sort_by == "line":
            refs.sort(key=lambda r: (r.get("file", ""), r.get("line", 0)))
        # Par défaut: criticality (déjà trié par l'analyzer)

        result["references"] = refs
        return result

    except Exception as e:
        logger.error(f"Error in smart_references: {e}")
        return {
            "error": f"Analysis error: {e}",
            "query": {"file": file_path, "line": line, "character": character},
            "references": [],
            "summary": {"total_references": 0},
        }


# =============================================================================
# OUTIL HYBRIDE 2: SMART_CALLERS
# =============================================================================

def smart_callers(
    db,
    file_path: str,
    line: int,
    character: int,
    max_depth: int = 3,
    include_patterns: bool = True
) -> dict[str, Any]:
    """
    Trouve les appelants d'une fonction avec enrichissement complet.

    Combine LSP incomingCalls + enrichissement AgentDB pour fournir:
    - Liste des appelants séparés en critiques/normaux
    - Historique des erreurs pour chaque appelant
    - Patterns potentiellement violés

    Avantages vs get_symbol_callers:
    - Utilise le call hierarchy LSP (plus précis)
    - Inclut les patterns violés
    - Séparation claire critiques/normaux

    Args:
        db: Connexion à la base
        file_path: Chemin du fichier
        line: Numéro de ligne (1-based)
        character: Position dans la ligne (1-based)
        max_depth: Profondeur maximale de traversée
        include_patterns: Inclure les patterns violés

    Returns:
        Dict avec query, callers{critical, normal}, summary
    """
    from agentdb.hybrid_lsp import create_hybrid_analyzer

    try:
        analyzer = create_hybrid_analyzer(db)
        result = analyzer.smart_callers(file_path, line, character, max_depth)

        # Si patterns non demandés, les retirer
        if not include_patterns:
            for caller_list in result.get("callers", {}).values():
                for caller in caller_list:
                    caller.pop("patterns_violated", None)

        return result

    except Exception as e:
        logger.error(f"Error in smart_callers: {e}")
        return {
            "error": f"Analysis error: {e}",
            "query": {"file": file_path, "line": line, "character": character},
            "callers": {"critical": [], "normal": []},
            "summary": {"total_callers": 0},
        }


# =============================================================================
# OUTIL HYBRIDE 3: IMPACT_ANALYSIS_V2
# =============================================================================

def impact_analysis_v2(
    db,
    file_path: str,
    changes: Optional[list[str]] = None,
    include_similar: bool = True,
    include_historical: bool = True
) -> dict[str, Any]:
    """
    Analyse d'impact de nouvelle génération.

    Combine toutes les sources de données disponibles:
    - LSP: Références précises, hiérarchie d'appels
    - AgentDB: Historique des bugs, patterns similaires
    - Git: Activité récente, contributeurs

    Fournit un score de risque calculé avec les facteurs expliqués.

    Avantages vs get_file_impact:
    - Score de risque quantifié (0-100)
    - Facteurs de risque expliqués
    - Changements similaires passés
    - Historique des bugs intégré

    Args:
        db: Connexion à la base
        file_path: Chemin du fichier modifié
        changes: Liste des modifications (code diff lines)
        include_similar: Inclure les changements similaires passés
        include_historical: Inclure l'historique des bugs

    Returns:
        Dict avec file, direct_references, call_hierarchy,
        historical_bugs, similar_changes, risk_score, risk_factors
    """
    from agentdb.hybrid_lsp import create_hybrid_analyzer

    try:
        analyzer = create_hybrid_analyzer(db)
        result = analyzer.impact_analysis_v2(file_path, changes)

        # Filtrer selon les options
        if not include_similar:
            result["similar_changes"] = []
        if not include_historical:
            result["historical_bugs"] = []

        return result

    except Exception as e:
        logger.error(f"Error in impact_analysis_v2: {e}")
        return {
            "error": f"Analysis error: {e}",
            "file": file_path,
            "direct_references": [],
            "call_hierarchy": [],
            "historical_bugs": [],
            "similar_changes": [],
            "risk_score": 0,
            "risk_factors": [],
        }


# =============================================================================
# OUTIL HYBRIDE 4: SMART_SEARCH
# =============================================================================

def smart_search(
    db,
    query: str,
    kind: Optional[str] = None,
    module: Optional[str] = None,
    file_pattern: Optional[str] = None,
    limit: int = 50,
    include_metrics: bool = False
) -> dict[str, Any]:
    """
    Recherche hybride de symboles.

    Utilise LSP workspaceSymbol quand disponible (plus rapide),
    avec fallback sur AgentDB pour les filtres avancés.

    Avantages vs search_symbols:
    - Plus rapide avec LSP
    - Filtres avancés via AgentDB
    - Métriques optionnelles
    - Source indiquée (lsp/agentdb/hybrid)

    Args:
        db: Connexion à la base
        query: Pattern de recherche (supporte * et ?)
        kind: Type de symbole (function, class, etc.)
        module: Filtrer par module
        file_pattern: Pattern glob pour le fichier
        limit: Nombre max de résultats
        include_metrics: Inclure les métriques de chaque fichier

    Returns:
        Dict avec query, results[], total, source
    """
    from agentdb.hybrid_lsp import create_hybrid_analyzer

    try:
        analyzer = create_hybrid_analyzer(db)
        result = analyzer.smart_search(query, kind, module, limit)

        # Filtrer par file_pattern si spécifié
        if file_pattern:
            import fnmatch
            result["results"] = [
                r for r in result.get("results", [])
                if fnmatch.fnmatch(r.get("file", ""), file_pattern)
            ]
            result["total"] = len(result["results"])

        # Ajouter les métriques si demandé
        if include_metrics:
            for r in result.get("results", []):
                file_path = r.get("file", "")
                metrics = _get_quick_metrics(db, file_path)
                if metrics:
                    r["metrics"] = metrics

        return result

    except Exception as e:
        logger.error(f"Error in smart_search: {e}")
        return {
            "error": f"Search error: {e}",
            "query": query,
            "results": [],
            "total": 0,
            "source": "error",
        }


def _get_quick_metrics(db, file_path: str) -> Optional[dict]:
    """Récupère des métriques rapides pour un fichier."""
    try:
        row = db.fetch_one(
            """
            SELECT lines_code, complexity_avg, is_critical
            FROM files WHERE path LIKE ?
            """,
            (f"%{file_path}",),
        )
        if row:
            return {
                "lines": row.get("lines_code", 0),
                "complexity": row.get("complexity_avg", 0),
                "is_critical": bool(row.get("is_critical", False)),
            }
    except Exception:
        pass
    return None


# =============================================================================
# OUTIL HYBRIDE 5: GET_RISK_ASSESSMENT
# =============================================================================

def get_risk_assessment(
    db,
    file_paths: list[str],
    include_recommendations: bool = True
) -> dict[str, Any]:
    """
    Évalue le risque d'un ensemble de modifications.

    Analyse plusieurs fichiers et produit un score de risque global
    avec des recommandations pour réduire les risques.

    Args:
        db: Connexion à la base
        file_paths: Liste des fichiers modifiés
        include_recommendations: Inclure les recommandations

    Returns:
        Dict avec files[], overall_risk_score, risk_factors, recommendations
    """
    from agentdb.hybrid_lsp import create_hybrid_analyzer

    analyzer = create_hybrid_analyzer(db)
    enricher = analyzer.enricher

    files_assessment = []
    total_references = 0
    total_critical = 0
    total_errors = 0
    all_risk_factors = []

    for file_path in file_paths:
        # Analyser chaque fichier
        file_info = enricher._get_file_info(file_path)
        error_count = enricher._count_recent_errors(file_path)

        # Compter les références (simplifié)
        ref_count = _count_file_references(db, file_path)

        # Calculer le risque individuel
        risk_score, factors = enricher.calculate_risk_score(
            file_path,
            ref_count,
            1 if file_info and file_info.get("is_critical") else 0,
            error_count
        )

        files_assessment.append({
            "file": file_path,
            "risk_score": risk_score,
            "risk_factors": factors,
            "is_critical": bool(file_info.get("is_critical")) if file_info else False,
            "references_count": ref_count,
            "error_count": error_count,
        })

        total_references += ref_count
        total_critical += 1 if file_info and file_info.get("is_critical") else 0
        total_errors += error_count
        all_risk_factors.extend(factors)

    # Score global (moyenne pondérée)
    if files_assessment:
        overall_score = sum(f["risk_score"] for f in files_assessment) / len(files_assessment)
        # Bonus pour le nombre de fichiers
        if len(files_assessment) > 5:
            overall_score = min(overall_score + 10, 100)
    else:
        overall_score = 0

    result = {
        "files": files_assessment,
        "overall_risk_score": round(overall_score, 1),
        "summary": {
            "total_files": len(files_assessment),
            "critical_files": total_critical,
            "total_references": total_references,
            "total_historical_errors": total_errors,
        },
        "risk_factors": list(set(all_risk_factors)),  # Unique factors
    }

    if include_recommendations:
        result["recommendations"] = _generate_recommendations(
            overall_score, files_assessment, all_risk_factors
        )

    return result


def _count_file_references(db, file_path: str) -> int:
    """Compte le nombre de références à un fichier."""
    try:
        row = db.fetch_one(
            """
            SELECT COUNT(*) as cnt
            FROM file_relations
            WHERE target_file_id = (
                SELECT id FROM files WHERE path LIKE ?
            )
            """,
            (f"%{file_path}",),
        )
        return row.get("cnt", 0) if row else 0
    except Exception:
        return 0


def _generate_recommendations(
    score: float,
    files: list[dict],
    factors: list[str]
) -> list[str]:
    """Génère des recommandations basées sur l'analyse de risque."""
    recommendations = []

    if score >= 70:
        recommendations.append(
            "HIGH RISK: Consider splitting this change into smaller PRs"
        )

    if any("Critical file" in f for f in factors):
        recommendations.append(
            "Review critical files changes with extra care"
        )

    if any("High reference count" in f for f in factors):
        recommendations.append(
            "Run comprehensive tests - many files depend on these changes"
        )

    if any("error history" in f.lower() for f in factors):
        recommendations.append(
            "Check error_history for similar past bugs before merging"
        )

    if any("High complexity" in f for f in factors):
        recommendations.append(
            "Consider refactoring complex functions to reduce risk"
        )

    if len(files) > 10:
        recommendations.append(
            "Large changeset - ensure adequate test coverage"
        )

    if not recommendations:
        recommendations.append("Low risk change - standard review process")

    return recommendations


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Nouveaux outils hybrides
    "smart_references",
    "smart_callers",
    "impact_analysis_v2",
    "smart_search",
    "get_risk_assessment",
]
