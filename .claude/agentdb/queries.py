"""
AgentDB - Requêtes complexes de traversée du graphe.

Ce module contient les requêtes avancées :
- Traversée récursive du graphe (callers, callees)
- Analyse d'impact
- Requêtes historiques agrégées
- Recherche dans la base de connaissances

Ces requêtes utilisent principalement des CTE récursives
pour parcourir le graphe de dépendances.

Usage:
    db = Database("...")
    graph = GraphQueries(db)

    # Trouver tous les appelants jusqu'à 3 niveaux
    callers = graph.get_symbol_callers("lcd_init", max_depth=3)

    # Calculer l'impact d'un fichier
    impact = graph.get_file_impact("src/lcd/init.c")
"""

from __future__ import annotations

from typing import Any, Optional

from .db import Database
from .models import CallerInfo, ImpactAnalysis, Symbol, File


# =============================================================================
# SQL TEMPLATES
# =============================================================================

# Requête récursive pour trouver les appelants
SQL_GET_CALLERS = """
WITH RECURSIVE callers AS (
    -- Cas de base : appelants directs
    SELECT
        s.id,
        s.name,
        s.kind,
        f.path as file_path,
        r.location_line,
        1 as depth
    FROM symbols s
    JOIN relations r ON r.source_id = s.id
    JOIN files f ON s.file_id = f.id
    WHERE r.target_id = :symbol_id
    AND r.relation_type = 'calls'

    UNION ALL

    -- Cas récursif : appelants des appelants
    SELECT
        s.id,
        s.name,
        s.kind,
        f.path as file_path,
        r.location_line,
        c.depth + 1 as depth
    FROM symbols s
    JOIN relations r ON r.source_id = s.id
    JOIN files f ON s.file_id = f.id
    JOIN callers c ON r.target_id = c.id
    WHERE r.relation_type = 'calls'
    AND c.depth < :max_depth
)
SELECT DISTINCT * FROM callers
ORDER BY depth, name;
"""

# Requête récursive pour trouver les appelés
SQL_GET_CALLEES = """
WITH RECURSIVE callees AS (
    SELECT
        s.id,
        s.name,
        s.kind,
        f.path as file_path,
        r.location_line,
        1 as depth
    FROM symbols s
    JOIN relations r ON r.target_id = s.id
    JOIN files f ON s.file_id = f.id
    WHERE r.source_id = :symbol_id
    AND r.relation_type = 'calls'

    UNION ALL

    SELECT
        s.id,
        s.name,
        s.kind,
        f.path as file_path,
        r.location_line,
        c.depth + 1 as depth
    FROM symbols s
    JOIN relations r ON r.target_id = s.id
    JOIN files f ON s.file_id = f.id
    JOIN callees c ON r.source_id = c.id
    WHERE r.relation_type = 'calls'
    AND c.depth < :max_depth
)
SELECT DISTINCT * FROM callees
ORDER BY depth, name;
"""

# Requête pour l'impact d'un fichier
SQL_FILE_IMPACT_BY_INCLUDES = """
SELECT DISTINCT f2.id, f2.path, 'includes' as reason
FROM files f1
JOIN file_relations fr ON fr.target_file_id = f1.id
JOIN files f2 ON fr.source_file_id = f2.id
WHERE f1.path = :file_path
AND fr.relation_type IN ('includes', 'imports');
"""

SQL_FILE_IMPACT_BY_CALLS = """
SELECT DISTINCT f2.id, f2.path, s2.name as symbol_name, 'calls' as reason
FROM files f1
JOIN symbols s1 ON s1.file_id = f1.id
JOIN relations r ON r.target_id = s1.id
JOIN symbols s2 ON r.source_id = s2.id
JOIN files f2 ON s2.file_id = f2.id
WHERE f1.path = :file_path
AND r.relation_type = 'calls'
AND f2.id != f1.id;
"""

# Requête pour l'arbre d'includes
SQL_INCLUDE_TREE = """
WITH RECURSIVE include_tree AS (
    SELECT
        f.id,
        f.path,
        0 as depth,
        f.path as root_path
    FROM files f
    WHERE f.path = :file_path

    UNION ALL

    SELECT
        f2.id,
        f2.path,
        it.depth + 1,
        it.root_path
    FROM file_relations fr
    JOIN include_tree it ON fr.source_file_id = it.id
    JOIN files f2 ON fr.target_file_id = f2.id
    WHERE fr.relation_type = 'includes'
    AND it.depth < :max_depth
)
SELECT * FROM include_tree
WHERE depth > 0
ORDER BY depth, path;
"""


# =============================================================================
# GRAPH QUERIES
# =============================================================================

class GraphQueries:
    """
    Requêtes de traversée du graphe de dépendances.

    Utilisé principalement par l'Agent Analyzer pour :
    - Calculer l'impact des modifications
    - Trouver les chemins critiques
    - Analyser les dépendances
    """

    def __init__(self, db: Database) -> None:
        """
        Initialise avec une connexion DB.

        Args:
            db: Instance de Database
        """
        self.db = db

    def get_symbol_callers(
        self,
        symbol_name: str,
        file_path: Optional[str] = None,
        max_depth: int = 3,
        include_indirect: bool = True
    ) -> dict[str, Any]:
        """
        Trouve tous les appelants d'un symbole (récursif).

        Args:
            symbol_name: Nom du symbole
            file_path: Fichier pour désambiguïser (optionnel)
            max_depth: Profondeur max de traversée
            include_indirect: Inclure les appels indirects

        Returns:
            Dict avec le symbole, les callers par niveau, et un résumé
        """
        # TODO: Implémenter avec SQL_GET_CALLERS
        # 1. Trouver le symbol_id depuis symbol_name (et file_path si fourni)
        # 2. Exécuter la requête récursive
        # 3. Organiser les résultats par niveau
        # 4. Calculer le résumé
        pass

    def get_symbol_callees(
        self,
        symbol_name: str,
        file_path: Optional[str] = None,
        max_depth: int = 2
    ) -> dict[str, Any]:
        """
        Trouve tous les symboles appelés par un symbole (récursif).

        Args:
            symbol_name: Nom du symbole
            file_path: Fichier pour désambiguïser
            max_depth: Profondeur max

        Returns:
            Dict avec le symbole, les callees par niveau, et les types utilisés
        """
        # TODO: Implémenter avec SQL_GET_CALLEES
        pass

    def get_file_impact(
        self,
        file_path: str,
        include_transitive: bool = True,
        max_depth: int = 3
    ) -> ImpactAnalysis:
        """
        Calcule l'impact de la modification d'un fichier.

        Args:
            file_path: Chemin du fichier
            include_transitive: Inclure les impacts transitifs
            max_depth: Profondeur max pour le transitif

        Returns:
            ImpactAnalysis avec direct, transitive, et include impacts
        """
        # TODO: Implémenter
        # 1. Impact par includes (SQL_FILE_IMPACT_BY_INCLUDES)
        # 2. Impact par calls (SQL_FILE_IMPACT_BY_CALLS)
        # 3. Si transitive, calculer les impacts de niveau 2+
        # 4. Identifier les fichiers critiques impactés
        pass

    def get_include_tree(self, file_path: str, max_depth: int = 5) -> dict[str, Any]:
        """
        Récupère l'arbre d'inclusion d'un fichier.

        Args:
            file_path: Chemin du fichier racine
            max_depth: Profondeur max

        Returns:
            Arbre des fichiers inclus
        """
        # TODO: Implémenter avec SQL_INCLUDE_TREE
        pass

    def get_type_users(
        self,
        type_name: str,
        file_path: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Trouve toutes les fonctions qui utilisent un type.

        Args:
            type_name: Nom du type (struct, class, enum)
            file_path: Fichier du type (optionnel)

        Returns:
            Liste des symboles utilisant ce type
        """
        # TODO: Implémenter avec requête sur relation_type IN (uses_type, returns_type, has_param_type)
        pass

    def get_dependency_chain(
        self,
        from_symbol: str,
        to_symbol: str
    ) -> Optional[list[dict[str, Any]]]:
        """
        Trouve le chemin de dépendance entre deux symboles.

        Args:
            from_symbol: Symbole de départ
            to_symbol: Symbole d'arrivée

        Returns:
            Chemin (liste de symboles) ou None si pas de chemin
        """
        # TODO: Implémenter avec BFS ou DFS récursif
        pass

    def get_critical_path_symbols(self) -> list[Symbol]:
        """
        Récupère les symboles dans des chemins critiques.

        Returns:
            Liste des symboles dans des fichiers critiques
        """
        # TODO: JOIN symbols avec files WHERE is_critical = 1
        pass


# =============================================================================
# HISTORY QUERIES
# =============================================================================

class HistoryQueries:
    """
    Requêtes sur l'historique et les métriques.

    Utilisé principalement par les Agents Security et Risk pour :
    - Détecter les régressions
    - Analyser les patterns d'erreurs
    - Évaluer la santé des modules
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_error_statistics(
        self,
        file_path: Optional[str] = None,
        module: Optional[str] = None,
        days: int = 180
    ) -> dict[str, Any]:
        """
        Calcule les statistiques d'erreurs.

        Args:
            file_path: Filtrer par fichier
            module: Filtrer par module
            days: Période en jours

        Returns:
            Statistiques: total, par type, par sévérité, taux de régression
        """
        # TODO: Implémenter avec GROUP BY
        pass

    def get_error_trends(
        self,
        module: Optional[str] = None,
        granularity: str = "month"
    ) -> list[dict[str, Any]]:
        """
        Calcule les tendances d'erreurs dans le temps.

        Args:
            module: Filtrer par module
            granularity: "day", "week", ou "month"

        Returns:
            Liste de {period, count, by_severity}
        """
        # TODO: Implémenter avec strftime pour grouper par période
        pass

    def get_similar_errors(
        self,
        error_type: str,
        file_path: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Trouve des erreurs similaires passées.

        Args:
            error_type: Type d'erreur
            file_path: Fichier concerné

        Returns:
            Liste d'erreurs similaires avec leurs résolutions
        """
        # TODO: SELECT WHERE error_type = ? avec ranking
        pass

    def get_high_risk_files(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Identifie les fichiers à haut risque.

        Critères:
        - Critiques
        - Beaucoup d'erreurs passées
        - Haute complexité
        - Beaucoup de modifications récentes

        Args:
            limit: Nombre max de résultats

        Returns:
            Liste de fichiers avec score de risque
        """
        # TODO: Implémenter avec score composite
        pass

    def get_regression_candidates(
        self,
        file_path: str,
        error_type: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Trouve les erreurs passées qui pourraient être des régressions.

        Args:
            file_path: Fichier à vérifier
            error_type: Type d'erreur spécifique (optionnel)

        Returns:
            Liste d'erreurs passées potentiellement régressées
        """
        # TODO: Chercher les erreurs résolues sur ce fichier
        pass

    def get_pipeline_statistics(self, days: int = 30) -> dict[str, Any]:
        """
        Calcule les statistiques des runs du pipeline.

        Args:
            days: Période en jours

        Returns:
            Stats: total runs, success rate, avg score, etc.
        """
        # TODO: Agrégation sur pipeline_runs
        pass


# =============================================================================
# KNOWLEDGE QUERIES
# =============================================================================

class KnowledgeQueries:
    """
    Requêtes sur la base de connaissances.

    Utilisé principalement par l'Agent Reviewer pour :
    - Vérifier le respect des patterns
    - Consulter les décisions architecturales
    - Appliquer les conventions
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_applicable_patterns(
        self,
        file_path: str,
        module: Optional[str] = None,
        category: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Récupère tous les patterns applicables à un fichier.

        Args:
            file_path: Chemin du fichier
            module: Module du fichier
            category: Filtrer par catégorie (optionnel)

        Returns:
            Liste de patterns (project + module + file specific)
        """
        # TODO: Implémenter avec GLOB matching
        pass

    def get_applicable_adrs(
        self,
        module: Optional[str] = None,
        file_path: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Récupère les ADRs applicables.

        Args:
            module: Filtrer par module
            file_path: Filtrer par fichier

        Returns:
            Liste d'ADRs acceptées et applicables
        """
        # TODO: Implémenter avec LIKE sur JSON
        pass

    def check_pattern_compliance(
        self,
        file_path: str,
        code_content: str
    ) -> list[dict[str, Any]]:
        """
        Vérifie la conformité du code aux patterns.

        Args:
            file_path: Chemin du fichier
            code_content: Contenu du code

        Returns:
            Liste des violations {pattern, rule, line, message}
        """
        # TODO: Implémenter la vérification des règles
        pass

    def get_module_conventions(self, module: str) -> dict[str, Any]:
        """
        Récupère toutes les conventions d'un module.

        Args:
            module: Nom du module

        Returns:
            Dict avec patterns, ADRs, et critical paths
        """
        # TODO: Agréger patterns + ADRs + critical_paths pour le module
        pass

    def search_patterns(
        self,
        query: str,
        limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        Recherche des patterns par texte.

        Args:
            query: Terme de recherche
            limit: Nombre max de résultats

        Returns:
            Liste de patterns matchant
        """
        # TODO: LIKE sur title, description, rules_json
        pass


# =============================================================================
# FILE CONTEXT QUERY
# =============================================================================

class FileContextQuery:
    """
    Requête composite pour get_file_context (l'outil MCP le plus utilisé).

    Agrège toutes les informations sur un fichier en une seule structure.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self.graph = GraphQueries(db)
        self.history = HistoryQueries(db)
        self.knowledge = KnowledgeQueries(db)

    def get_context(
        self,
        file_path: str,
        include_symbols: bool = True,
        include_dependencies: bool = True,
        include_history: bool = True,
        include_patterns: bool = True
    ) -> dict[str, Any]:
        """
        Récupère le contexte complet d'un fichier.

        Args:
            file_path: Chemin du fichier
            include_symbols: Inclure la liste des symboles
            include_dependencies: Inclure les dépendances
            include_history: Inclure l'historique des erreurs
            include_patterns: Inclure les patterns applicables

        Returns:
            Dict complet avec file, symbols, dependencies, history, patterns, adrs
        """
        # TODO: Implémenter l'agrégation
        # 1. Récupérer le fichier depuis files
        # 2. Si include_symbols: récupérer les symboles
        # 3. Si include_dependencies: calculer includes/included_by/calls_to/called_by
        # 4. Si include_history: récupérer error_history
        # 5. Si include_patterns: récupérer patterns + ADRs
        # 6. Construire et retourner le dict complet
        pass
