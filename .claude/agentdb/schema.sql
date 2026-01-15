-- ============================================================================
-- AGENTDB - SCHÉMA COMPLET
-- Version: 2.0
-- Description: Base de données contextuelle pour le système multi-agents
-- ============================================================================

-- ============================================================================
-- PRAGMA CONFIGURATION
-- ============================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;  -- 64MB cache
PRAGMA temp_store = MEMORY;

-- ============================================================================
-- PILIER 1 : LE GRAPHE DE DÉPENDANCES
-- ============================================================================

-- Table des fichiers
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identification
    path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    extension TEXT,

    -- Classification
    module TEXT,
    layer TEXT,
    file_type TEXT NOT NULL DEFAULT 'source',
    language TEXT,

    -- Criticité
    is_critical BOOLEAN DEFAULT 0,
    criticality_reason TEXT,
    security_sensitive BOOLEAN DEFAULT 0,

    -- Métriques de code
    lines_total INTEGER DEFAULT 0,
    lines_code INTEGER DEFAULT 0,
    lines_comment INTEGER DEFAULT 0,
    lines_blank INTEGER DEFAULT 0,
    complexity_sum INTEGER DEFAULT 0,
    complexity_avg REAL DEFAULT 0,
    complexity_max INTEGER DEFAULT 0,

    -- Métriques d'activité
    commits_30d INTEGER DEFAULT 0,
    commits_90d INTEGER DEFAULT 0,
    commits_365d INTEGER DEFAULT 0,
    contributors_json TEXT,
    last_modified TEXT,
    created_at TEXT,

    -- Métriques de qualité
    has_tests BOOLEAN DEFAULT 0,
    test_file_path TEXT,
    documentation_score INTEGER DEFAULT 0,
    technical_debt_score INTEGER DEFAULT 0,

    -- Métadonnées
    content_hash TEXT,
    indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
    index_version INTEGER DEFAULT 1
);

-- Table des symboles
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,

    -- Identification
    name TEXT NOT NULL,
    qualified_name TEXT,

    -- Classification
    kind TEXT NOT NULL,

    -- Localisation
    line_start INTEGER,
    line_end INTEGER,
    column_start INTEGER,
    column_end INTEGER,

    -- Signature (fonctions)
    signature TEXT,
    return_type TEXT,
    parameters_json TEXT,
    is_variadic BOOLEAN DEFAULT 0,

    -- Structure (struct/class/enum)
    fields_json TEXT,
    base_classes_json TEXT,
    size_bytes INTEGER,

    -- Visibilité
    visibility TEXT DEFAULT 'public',
    is_exported BOOLEAN DEFAULT 0,
    is_static BOOLEAN DEFAULT 0,
    is_inline BOOLEAN DEFAULT 0,

    -- Métriques
    complexity INTEGER DEFAULT 0,
    lines_of_code INTEGER DEFAULT 0,
    cognitive_complexity INTEGER DEFAULT 0,
    nesting_depth INTEGER DEFAULT 0,

    -- Documentation
    doc_comment TEXT,
    has_doc BOOLEAN DEFAULT 0,
    doc_quality INTEGER DEFAULT 0,

    -- Métadonnées
    attributes_json TEXT,
    hash TEXT,
    indexed_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    UNIQUE(file_id, name, kind, line_start)
);

-- Table des relations entre symboles
CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,

    -- Type de relation
    relation_type TEXT NOT NULL,

    -- Localisation
    location_file_id INTEGER,
    location_line INTEGER,
    location_column INTEGER,

    -- Métadonnées
    count INTEGER DEFAULT 1,
    is_direct BOOLEAN DEFAULT 1,
    is_conditional BOOLEAN DEFAULT 0,
    context TEXT,

    FOREIGN KEY (source_id) REFERENCES symbols(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES symbols(id) ON DELETE CASCADE,
    FOREIGN KEY (location_file_id) REFERENCES files(id) ON DELETE SET NULL
);

-- Table des relations entre fichiers
CREATE TABLE IF NOT EXISTS file_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_id INTEGER NOT NULL,
    target_file_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    is_direct BOOLEAN DEFAULT 1,
    line_number INTEGER,

    FOREIGN KEY (source_file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (target_file_id) REFERENCES files(id) ON DELETE CASCADE,
    UNIQUE(source_file_id, target_file_id, relation_type)
);

-- ============================================================================
-- PILIER 2 : LA MÉMOIRE HISTORIQUE
-- ============================================================================

-- Historique des erreurs
CREATE TABLE IF NOT EXISTS error_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identification
    file_id INTEGER,
    file_path TEXT NOT NULL,
    symbol_name TEXT,
    symbol_id INTEGER,

    -- Classification
    error_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    cwe_id TEXT,

    -- Description
    title TEXT NOT NULL,
    description TEXT,
    root_cause TEXT,
    symptoms TEXT,

    -- Résolution
    resolution TEXT,
    prevention TEXT,
    fix_commit TEXT,
    fix_diff TEXT,

    -- Contexte
    discovered_at TEXT NOT NULL,
    resolved_at TEXT,
    discovered_by TEXT,
    reported_in TEXT,
    jira_ticket TEXT,
    environment TEXT,

    -- Commits
    introducing_commit TEXT,
    related_commits_json TEXT,

    -- Métadonnées
    is_regression BOOLEAN DEFAULT 0,
    original_error_id INTEGER,
    tags_json TEXT,
    extra_data_json TEXT,

    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE SET NULL,
    FOREIGN KEY (original_error_id) REFERENCES error_history(id) ON DELETE SET NULL
);

-- Historique des runs du pipeline
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,

    -- Contexte Git
    commit_hash TEXT NOT NULL,
    commit_message TEXT,
    commit_author TEXT,
    branch_source TEXT,
    branch_target TEXT,
    merge_type TEXT,

    -- Contexte JIRA
    jira_key TEXT,
    jira_type TEXT,
    jira_summary TEXT,

    -- Résultats
    status TEXT NOT NULL,
    overall_score INTEGER,
    recommendation TEXT,

    -- Scores par agent
    score_analyzer INTEGER,
    score_security INTEGER,
    score_reviewer INTEGER,
    score_risk INTEGER,

    -- Issues
    issues_critical INTEGER DEFAULT 0,
    issues_high INTEGER DEFAULT 0,
    issues_medium INTEGER DEFAULT 0,
    issues_low INTEGER DEFAULT 0,
    issues_json TEXT,

    -- Fichiers
    files_analyzed INTEGER,
    files_json TEXT,

    -- Rapports
    report_path TEXT,
    report_json_path TEXT,
    context_path TEXT,

    -- Timing
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms INTEGER,

    -- Métadonnées
    trigger TEXT,
    pipeline_version TEXT,
    agents_used_json TEXT
);

-- Snapshot temporaire
CREATE TABLE IF NOT EXISTS snapshot_symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    symbol_name TEXT NOT NULL,
    symbol_kind TEXT NOT NULL,
    signature TEXT,
    complexity INTEGER,
    line_start INTEGER,
    line_end INTEGER,
    hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================================
-- PILIER 3 : LA BASE DE CONNAISSANCES
-- ============================================================================

-- Patterns du projet
CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identification
    name TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,

    -- Scope
    scope TEXT DEFAULT 'project',
    module TEXT,
    file_pattern TEXT,

    -- Description
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    rationale TEXT,

    -- Exemples
    good_example TEXT,
    bad_example TEXT,
    explanation TEXT,

    -- Règles
    rules_json TEXT,

    -- Métadonnées
    severity TEXT DEFAULT 'warning',
    is_active BOOLEAN DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,
    created_by TEXT,

    -- Références
    related_adr TEXT,
    external_link TEXT,
    examples_in_code_json TEXT
);

-- Décisions architecturales
CREATE TABLE IF NOT EXISTS architecture_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT UNIQUE NOT NULL,

    -- Statut
    status TEXT NOT NULL,
    superseded_by TEXT,

    -- Contenu
    title TEXT NOT NULL,
    context TEXT NOT NULL,
    decision TEXT NOT NULL,
    consequences TEXT,
    alternatives TEXT,

    -- Scope
    affected_modules_json TEXT,
    affected_files_json TEXT,

    -- Métadonnées
    date_proposed TEXT,
    date_decided TEXT,
    decided_by TEXT,
    stakeholders_json TEXT,

    -- Liens
    related_adrs_json TEXT,
    jira_tickets_json TEXT,
    documentation_link TEXT
);

-- Chemins critiques
CREATE TABLE IF NOT EXISTS critical_paths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT UNIQUE NOT NULL,
    reason TEXT NOT NULL,
    severity TEXT DEFAULT 'high',
    added_by TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================================
-- PILIER 4 : TABLES UTILITAIRES
-- ============================================================================

-- Métadonnées de la base
CREATE TABLE IF NOT EXISTS agentdb_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Insert initial meta
INSERT OR IGNORE INTO agentdb_meta (key, value) VALUES
    ('schema_version', '2.0'),
    ('created_at', datetime('now')),
    ('project_name', 'unknown'),
    ('project_language', 'unknown');

-- ============================================================================
-- INDEX POUR PERFORMANCE
-- ============================================================================

-- Index sur files
CREATE INDEX IF NOT EXISTS idx_files_module ON files(module);
CREATE INDEX IF NOT EXISTS idx_files_is_critical ON files(is_critical);
CREATE INDEX IF NOT EXISTS idx_files_language ON files(language);
CREATE INDEX IF NOT EXISTS idx_files_path_pattern ON files(path);

-- Index sur symbols
CREATE INDEX IF NOT EXISTS idx_symbols_file_id ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_symbols_file_kind ON symbols(file_id, kind);

-- Index sur relations
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_relations_source_type ON relations(source_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_relations_target_type ON relations(target_id, relation_type);

-- Index sur file_relations
CREATE INDEX IF NOT EXISTS idx_file_relations_source ON file_relations(source_file_id);
CREATE INDEX IF NOT EXISTS idx_file_relations_target ON file_relations(target_file_id);

-- Index sur error_history
CREATE INDEX IF NOT EXISTS idx_errors_file_id ON error_history(file_id);
CREATE INDEX IF NOT EXISTS idx_errors_file_path ON error_history(file_path);
CREATE INDEX IF NOT EXISTS idx_errors_type ON error_history(error_type);
CREATE INDEX IF NOT EXISTS idx_errors_severity ON error_history(severity);
CREATE INDEX IF NOT EXISTS idx_errors_discovered ON error_history(discovered_at);

-- Index sur pipeline_runs
CREATE INDEX IF NOT EXISTS idx_runs_commit ON pipeline_runs(commit_hash);
CREATE INDEX IF NOT EXISTS idx_runs_jira ON pipeline_runs(jira_key);
CREATE INDEX IF NOT EXISTS idx_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started ON pipeline_runs(started_at);

-- Index sur patterns
CREATE INDEX IF NOT EXISTS idx_patterns_category ON patterns(category);
CREATE INDEX IF NOT EXISTS idx_patterns_module ON patterns(module);
CREATE INDEX IF NOT EXISTS idx_patterns_active ON patterns(is_active);

-- Index sur architecture_decisions
CREATE INDEX IF NOT EXISTS idx_adr_status ON architecture_decisions(status);

-- Index sur snapshot
CREATE INDEX IF NOT EXISTS idx_snapshot_run ON snapshot_symbols(run_id);

-- ============================================================================
-- VUES UTILITAIRES
-- ============================================================================

-- Vue : Fichiers avec leurs stats de symboles
CREATE VIEW IF NOT EXISTS v_files_with_stats AS
SELECT
    f.*,
    COUNT(s.id) as symbol_count,
    SUM(CASE WHEN s.kind = 'function' THEN 1 ELSE 0 END) as function_count,
    SUM(CASE WHEN s.kind IN ('struct', 'class') THEN 1 ELSE 0 END) as type_count,
    AVG(s.complexity) as avg_complexity
FROM files f
LEFT JOIN symbols s ON s.file_id = f.id
GROUP BY f.id;

-- Vue : Symboles avec leur contexte fichier
CREATE VIEW IF NOT EXISTS v_symbols_with_context AS
SELECT
    s.*,
    f.path as file_path,
    f.module as file_module,
    f.is_critical as file_is_critical,
    f.language as file_language
FROM symbols s
JOIN files f ON s.file_id = f.id;

-- Vue : Relations avec noms des symboles
CREATE VIEW IF NOT EXISTS v_relations_named AS
SELECT
    r.id,
    r.relation_type,
    r.count,
    r.location_line,
    src.name as source_name,
    src.kind as source_kind,
    src_f.path as source_file,
    tgt.name as target_name,
    tgt.kind as target_kind,
    tgt_f.path as target_file
FROM relations r
JOIN symbols src ON r.source_id = src.id
JOIN symbols tgt ON r.target_id = tgt.id
JOIN files src_f ON src.file_id = src_f.id
JOIN files tgt_f ON tgt.file_id = tgt_f.id;

-- Vue : Erreurs récentes (30 jours)
CREATE VIEW IF NOT EXISTS v_recent_errors AS
SELECT * FROM error_history
WHERE discovered_at >= datetime('now', '-30 days')
ORDER BY discovered_at DESC;

-- Vue : Fichiers à risque (critiques + erreurs récentes)
CREATE VIEW IF NOT EXISTS v_high_risk_files AS
SELECT
    f.id,
    f.path,
    f.module,
    f.is_critical,
    f.complexity_avg,
    COUNT(e.id) as error_count,
    MAX(e.severity) as max_severity
FROM files f
LEFT JOIN error_history e ON e.file_id = f.id
    AND e.discovered_at >= datetime('now', '-180 days')
WHERE f.is_critical = 1 OR e.id IS NOT NULL
GROUP BY f.id
ORDER BY f.is_critical DESC, error_count DESC;

-- ============================================================================
-- PILIER 5 : ANALYSE INCRÉMENTALE
-- ============================================================================

-- Checkpoints d'analyse par branche
-- Stocke le dernier commit analysé pour chaque branche
CREATE TABLE IF NOT EXISTS analysis_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identification de la branche
    branch TEXT UNIQUE NOT NULL,

    -- Dernier commit analysé
    last_commit TEXT NOT NULL,
    last_commit_short TEXT,
    last_commit_message TEXT,

    -- Métadonnées
    last_analyzed_at TEXT NOT NULL DEFAULT (datetime('now')),
    analysis_count INTEGER DEFAULT 1,
    files_analyzed INTEGER DEFAULT 0,

    -- Contexte
    merge_base TEXT,           -- Point de divergence avec la branche cible
    target_branch TEXT,        -- Branche cible (main, develop, etc.)

    -- Informations du dernier run
    last_run_id TEXT,
    last_verdict TEXT,
    last_score INTEGER
);

-- Index pour performance
CREATE INDEX IF NOT EXISTS idx_checkpoints_branch ON analysis_checkpoints(branch);
CREATE INDEX IF NOT EXISTS idx_checkpoints_commit ON analysis_checkpoints(last_commit);

-- ============================================================================
-- PILIER 6 : INDEXATION INCRÉMENTALE
-- ============================================================================

-- Checkpoint d'indexation global
-- Une seule ligne qui stocke l'état de la dernière indexation complète
CREATE TABLE IF NOT EXISTS index_checkpoints (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- Force une seule ligne

    -- Dernier commit indexé
    last_commit TEXT NOT NULL,
    last_commit_short TEXT,
    last_commit_message TEXT,

    -- Statistiques
    files_indexed INTEGER DEFAULT 0,
    symbols_indexed INTEGER DEFAULT 0,
    relations_indexed INTEGER DEFAULT 0,

    -- Timing
    last_indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
    duration_seconds REAL DEFAULT 0,

    -- Mode utilisé (full ou incremental)
    index_mode TEXT DEFAULT 'full',

    -- Version du schéma pour compatibilité
    schema_version TEXT DEFAULT '2.0'
);

-- Index sur le commit pour recherche rapide
CREATE INDEX IF NOT EXISTS idx_index_checkpoints_commit ON index_checkpoints(last_commit);

-- ============================================================================
-- PILIER 7 : RECHERCHE SÉMANTIQUE (EMBEDDINGS)
-- ============================================================================

-- Embeddings des symboles (fonctions, classes, etc.)
-- Utilise sentence-transformers pour générer des vecteurs de 384 dimensions
CREATE TABLE IF NOT EXISTS symbol_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id INTEGER NOT NULL UNIQUE,

    -- Vecteur d'embedding (BLOB pour stockage compact)
    -- Format: float32 array serialisé en bytes (384 * 4 = 1536 bytes)
    embedding BLOB NOT NULL,

    -- Métadonnées de l'embedding
    model_name TEXT DEFAULT 'all-MiniLM-L6-v2',
    model_version TEXT DEFAULT '1.0',
    dimensions INTEGER DEFAULT 384,

    -- Source du texte utilisé pour l'embedding
    source_text_hash TEXT,  -- Hash du texte source pour invalidation

    -- Timing
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,

    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
);

-- Embeddings des fichiers (pour recherche par fichier entier)
CREATE TABLE IF NOT EXISTS file_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL UNIQUE,

    -- Vecteur d'embedding
    embedding BLOB NOT NULL,

    -- Métadonnées
    model_name TEXT DEFAULT 'all-MiniLM-L6-v2',
    model_version TEXT DEFAULT '1.0',
    dimensions INTEGER DEFAULT 384,

    -- Source
    source_type TEXT DEFAULT 'docstrings',  -- docstrings, code, combined
    source_text_hash TEXT,

    -- Timing
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,

    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- Cache de recherche sémantique (pour accélérer les requêtes répétées)
CREATE TABLE IF NOT EXISTS semantic_search_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Requête
    query_text TEXT NOT NULL,
    query_hash TEXT UNIQUE NOT NULL,  -- MD5 de la requête normalisée
    query_embedding BLOB NOT NULL,

    -- Résultats (JSON array des top-k résultats)
    results_json TEXT NOT NULL,
    result_count INTEGER,

    -- Configuration de la recherche
    search_type TEXT DEFAULT 'symbol',  -- symbol, file, hybrid
    top_k INTEGER DEFAULT 10,
    threshold REAL DEFAULT 0.5,

    -- Timing et validité
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,  -- NULL = jamais expire
    hit_count INTEGER DEFAULT 0,
    last_hit_at TEXT
);

-- Index pour performance des embeddings
CREATE INDEX IF NOT EXISTS idx_symbol_embeddings_symbol ON symbol_embeddings(symbol_id);
CREATE INDEX IF NOT EXISTS idx_symbol_embeddings_model ON symbol_embeddings(model_name, model_version);
CREATE INDEX IF NOT EXISTS idx_file_embeddings_file ON file_embeddings(file_id);
CREATE INDEX IF NOT EXISTS idx_semantic_cache_hash ON semantic_search_cache(query_hash);
CREATE INDEX IF NOT EXISTS idx_semantic_cache_expires ON semantic_search_cache(expires_at);

-- Vue : Symboles avec leurs embeddings
CREATE VIEW IF NOT EXISTS v_symbols_with_embeddings AS
SELECT
    s.id,
    s.name,
    s.kind,
    s.qualified_name,
    s.doc_comment,
    s.signature,
    f.path as file_path,
    f.module,
    CASE WHEN se.id IS NOT NULL THEN 1 ELSE 0 END as has_embedding
FROM symbols s
JOIN files f ON s.file_id = f.id
LEFT JOIN symbol_embeddings se ON se.symbol_id = s.id;

-- Vue : Statistiques des embeddings
CREATE VIEW IF NOT EXISTS v_embedding_stats AS
SELECT
    'symbols' as type,
    COUNT(*) as total,
    (SELECT COUNT(*) FROM symbol_embeddings) as with_embedding,
    ROUND(100.0 * (SELECT COUNT(*) FROM symbol_embeddings) / NULLIF(COUNT(*), 0), 2) as coverage_percent
FROM symbols
WHERE kind IN ('function', 'method', 'class', 'struct')
UNION ALL
SELECT
    'files' as type,
    COUNT(*) as total,
    (SELECT COUNT(*) FROM file_embeddings) as with_embedding,
    ROUND(100.0 * (SELECT COUNT(*) FROM file_embeddings) / NULLIF(COUNT(*), 0), 2) as coverage_percent
FROM files;

-- ============================================================================
-- PILIER 8 : PATTERN LEARNING (Apprentissage automatique)
-- ============================================================================

-- Patterns appris automatiquement à partir de l'historique
CREATE TABLE IF NOT EXISTS learned_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identification
    pattern_hash TEXT UNIQUE NOT NULL,  -- Hash unique du pattern
    name TEXT NOT NULL,                  -- Nom généré ou assigné
    category TEXT NOT NULL,              -- error_prone, performance, security, style

    -- Description
    description TEXT NOT NULL,
    detection_rule TEXT,                 -- Règle de détection (regex, AST query, etc.)
    detection_type TEXT DEFAULT 'heuristic',  -- heuristic, ast_pattern, ml_model

    -- Contexte
    language TEXT,                       -- Langage concerné (NULL = tous)
    file_pattern TEXT,                   -- Pattern de fichiers concernés
    symbol_kind TEXT,                    -- Type de symbole (function, class, etc.)

    -- Statistiques
    occurrence_count INTEGER DEFAULT 0,  -- Nombre de fois détecté
    fix_count INTEGER DEFAULT 0,         -- Nombre de fois corrigé
    false_positive_count INTEGER DEFAULT 0,
    confidence_score REAL DEFAULT 0.5,   -- Score de confiance (0-1)

    -- Exemple
    example_bad TEXT,                    -- Exemple de code problématique
    example_good TEXT,                   -- Exemple de correction
    example_file TEXT,                   -- Fichier d'exemple

    -- Métadonnées
    source TEXT DEFAULT 'auto',          -- auto, manual, imported
    is_active BOOLEAN DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,
    last_detected_at TEXT,

    -- Liens
    related_error_types_json TEXT,       -- Types d'erreurs associés
    related_patterns_json TEXT           -- Patterns similaires
);

-- Occurrences de patterns détectés
CREATE TABLE IF NOT EXISTS pattern_occurrences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Liens
    pattern_id INTEGER NOT NULL,
    file_id INTEGER,
    symbol_id INTEGER,

    -- Localisation
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    code_snippet TEXT,                   -- Extrait de code concerné

    -- Contexte
    commit_hash TEXT,                    -- Commit où détecté
    branch TEXT,

    -- Statut
    status TEXT DEFAULT 'detected',      -- detected, confirmed, fixed, false_positive
    fixed_at TEXT,
    fixed_by TEXT,
    fix_commit TEXT,

    -- Métadonnées
    detected_at TEXT NOT NULL DEFAULT (datetime('now')),
    detection_context_json TEXT,         -- Contexte additionnel

    FOREIGN KEY (pattern_id) REFERENCES learned_patterns(id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE SET NULL
);

-- Historique des corrections (pour apprendre des fixes)
CREATE TABLE IF NOT EXISTS fix_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identification
    fix_hash TEXT UNIQUE,                -- Hash du fix pour déduplication

    -- Contexte de l'erreur
    error_type TEXT NOT NULL,
    error_file TEXT NOT NULL,
    error_line INTEGER,
    error_description TEXT,

    -- Code avant/après
    code_before TEXT NOT NULL,
    code_after TEXT NOT NULL,
    diff_unified TEXT,                   -- Diff au format unifié

    -- Contexte Git
    commit_hash TEXT,
    commit_message TEXT,
    commit_author TEXT,
    commit_date TEXT,

    -- Classification
    fix_type TEXT,                       -- refactor, bugfix, security, performance
    complexity TEXT DEFAULT 'simple',    -- simple, moderate, complex
    breaking_change BOOLEAN DEFAULT 0,

    -- Apprentissage
    learned_pattern_id INTEGER,          -- Pattern appris de ce fix
    similar_fixes_json TEXT,             -- Fixes similaires trouvés

    -- Métadonnées
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    source TEXT DEFAULT 'git',           -- git, manual, import

    FOREIGN KEY (learned_pattern_id) REFERENCES learned_patterns(id) ON DELETE SET NULL
);

-- Code smells détectés (anti-patterns courants)
CREATE TABLE IF NOT EXISTS code_smells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Localisation
    file_id INTEGER,
    file_path TEXT NOT NULL,
    symbol_id INTEGER,
    symbol_name TEXT,
    line_start INTEGER,
    line_end INTEGER,

    -- Classification
    smell_type TEXT NOT NULL,            -- long_method, god_class, duplicate_code, etc.
    severity TEXT DEFAULT 'medium',      -- low, medium, high, critical
    confidence REAL DEFAULT 0.7,

    -- Description
    description TEXT,
    suggestion TEXT,                     -- Suggestion de correction
    estimated_effort TEXT,               -- quick, moderate, significant

    -- Métriques associées
    metrics_json TEXT,                   -- Métriques qui ont déclenché la détection

    -- Statut
    status TEXT DEFAULT 'open',          -- open, acknowledged, fixed, wont_fix
    fixed_at TEXT,

    -- Métadonnées
    detected_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT,
    occurrence_count INTEGER DEFAULT 1,

    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE SET NULL
);

-- Feedback utilisateur pour améliorer l'apprentissage
CREATE TABLE IF NOT EXISTS learning_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Sujet du feedback
    feedback_type TEXT NOT NULL,         -- pattern, smell, suggestion, fix
    target_type TEXT NOT NULL,           -- learned_pattern, code_smell, pattern_occurrence
    target_id INTEGER NOT NULL,

    -- Feedback
    is_helpful BOOLEAN,                  -- Le pattern/suggestion était utile ?
    is_accurate BOOLEAN,                 -- La détection était correcte ?
    rating INTEGER,                      -- Score 1-5

    -- Commentaire
    comment TEXT,
    suggested_improvement TEXT,

    -- Contexte
    user_id TEXT,
    session_id TEXT,

    -- Métadonnées
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Index pour pattern learning
CREATE INDEX IF NOT EXISTS idx_learned_patterns_category ON learned_patterns(category);
CREATE INDEX IF NOT EXISTS idx_learned_patterns_language ON learned_patterns(language);
CREATE INDEX IF NOT EXISTS idx_learned_patterns_confidence ON learned_patterns(confidence_score);
CREATE INDEX IF NOT EXISTS idx_learned_patterns_active ON learned_patterns(is_active);

CREATE INDEX IF NOT EXISTS idx_pattern_occurrences_pattern ON pattern_occurrences(pattern_id);
CREATE INDEX IF NOT EXISTS idx_pattern_occurrences_file ON pattern_occurrences(file_id);
CREATE INDEX IF NOT EXISTS idx_pattern_occurrences_status ON pattern_occurrences(status);
CREATE INDEX IF NOT EXISTS idx_pattern_occurrences_detected ON pattern_occurrences(detected_at);

CREATE INDEX IF NOT EXISTS idx_fix_history_error_type ON fix_history(error_type);
CREATE INDEX IF NOT EXISTS idx_fix_history_commit ON fix_history(commit_hash);
CREATE INDEX IF NOT EXISTS idx_fix_history_learned ON fix_history(learned_pattern_id);

CREATE INDEX IF NOT EXISTS idx_code_smells_file ON code_smells(file_id);
CREATE INDEX IF NOT EXISTS idx_code_smells_type ON code_smells(smell_type);
CREATE INDEX IF NOT EXISTS idx_code_smells_severity ON code_smells(severity);
CREATE INDEX IF NOT EXISTS idx_code_smells_status ON code_smells(status);

CREATE INDEX IF NOT EXISTS idx_learning_feedback_target ON learning_feedback(target_type, target_id);

-- Vue : Patterns les plus fréquents
CREATE VIEW IF NOT EXISTS v_top_patterns AS
SELECT
    lp.id,
    lp.name,
    lp.category,
    lp.occurrence_count,
    lp.fix_count,
    lp.confidence_score,
    ROUND(100.0 * lp.fix_count / NULLIF(lp.occurrence_count, 0), 1) as fix_rate,
    COUNT(po.id) as active_occurrences
FROM learned_patterns lp
LEFT JOIN pattern_occurrences po ON po.pattern_id = lp.id AND po.status = 'detected'
WHERE lp.is_active = 1
GROUP BY lp.id
ORDER BY lp.occurrence_count DESC;

-- Vue : Code smells par fichier
CREATE VIEW IF NOT EXISTS v_smells_by_file AS
SELECT
    f.path,
    f.module,
    COUNT(cs.id) as smell_count,
    SUM(CASE WHEN cs.severity = 'critical' THEN 1 ELSE 0 END) as critical_count,
    SUM(CASE WHEN cs.severity = 'high' THEN 1 ELSE 0 END) as high_count,
    GROUP_CONCAT(DISTINCT cs.smell_type) as smell_types
FROM files f
JOIN code_smells cs ON cs.file_id = f.id
WHERE cs.status = 'open'
GROUP BY f.id
ORDER BY critical_count DESC, high_count DESC, smell_count DESC;

-- Vue : Efficacité du learning
CREATE VIEW IF NOT EXISTS v_learning_effectiveness AS
SELECT
    lp.category,
    COUNT(DISTINCT lp.id) as pattern_count,
    SUM(lp.occurrence_count) as total_occurrences,
    SUM(lp.fix_count) as total_fixes,
    AVG(lp.confidence_score) as avg_confidence,
    SUM(lp.false_positive_count) as total_false_positives,
    ROUND(100.0 * SUM(lp.false_positive_count) / NULLIF(SUM(lp.occurrence_count), 0), 2) as false_positive_rate
FROM learned_patterns lp
WHERE lp.is_active = 1
GROUP BY lp.category;
