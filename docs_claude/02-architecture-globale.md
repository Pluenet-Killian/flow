# Architecture Globale

> Visualisation complete du systeme AgentDB et de ses flux de donnees

---

## Diagramme d'Architecture Principal

```mermaid
flowchart TB
    subgraph External["Monde Externe"]
        USER[("Utilisateur")]
        GIT[("Repository Git")]
        IDE["IDE / CLI"]
    end

    subgraph AI["Couche Agent IA"]
        CLAUDE["Claude<br/>(Agent IA)"]
    end

    subgraph MCP["Couche MCP"]
        direction TB
        SERVER["MCP Server<br/>server.py"]

        subgraph TOOLS["10 Outils MCP"]
            T1["get_file_context"]
            T2["get_symbol_callers"]
            T3["get_symbol_callees"]
            T4["get_file_impact"]
            T5["get_error_history"]
            T6["get_patterns"]
            T7["get_architecture_decisions"]
            T8["search_symbols"]
            T9["get_file_metrics"]
            T10["get_module_summary"]
        end
    end

    subgraph CORE["Coeur AgentDB"]
        direction TB
        QUERIES["queries.py<br/>Traversee Graphe"]
        CRUD["crud.py<br/>Operations CRUD"]
        MODELS["models.py<br/>Modeles Donnees"]
        DB["db.py<br/>Connexion SQLite"]
        INDEXER["indexer.py<br/>Parseur Code"]
        CONFIG["config.py<br/>Configuration"]
    end

    subgraph SCRIPTS["Scripts Automatisation"]
        BOOTSTRAP["bootstrap.py<br/>9 Etapes Init"]
        UPDATE["update.py<br/>MAJ Incrementale"]
    end

    subgraph DATABASE["Base de Donnees SQLite"]
        direction TB

        subgraph P1["Pilier 1: Graphe"]
            FILES[(files)]
            SYMBOLS[(symbols)]
            RELATIONS[(relations)]
            FILE_REL[(file_relations)]
        end

        subgraph P2["Pilier 2: Memoire"]
            ERRORS[(error_history)]
            PIPELINE[(pipeline_runs)]
            SNAPSHOT[(snapshot_symbols)]
        end

        subgraph P3["Pilier 3: Connaissance"]
            PATTERNS[(patterns)]
            ADR[(architecture_decisions)]
            CRITICAL[(critical_paths)]
        end
    end

    subgraph PARSING["Outils de Parsing"]
        CTAGS["Universal Ctags<br/>(C/C++)"]
        AST["Python AST<br/>(Python)"]
    end

    %% Connexions Utilisateur
    USER -->|"Commits"| GIT
    USER -->|"Requetes"| IDE
    IDE -->|"Invoque"| CLAUDE

    %% Connexions Agent -> MCP
    CLAUDE <-->|"MCP Protocol<br/>JSON-RPC"| SERVER
    SERVER --> TOOLS

    %% Connexions MCP -> Core
    T1 & T2 & T3 & T4 --> QUERIES
    T5 & T6 & T7 --> CRUD
    T8 & T9 & T10 --> CRUD

    %% Connexions Core internes
    QUERIES --> CRUD
    CRUD --> MODELS
    CRUD --> DB
    INDEXER --> CRUD
    INDEXER --> CONFIG
    CONFIG -->|"Lit"| YAML[("agentdb.yaml")]

    %% Connexions Core -> DB
    DB <-->|"WAL Mode"| DATABASE

    %% Connexions Scripts
    BOOTSTRAP --> INDEXER
    BOOTSTRAP --> DB
    UPDATE --> INDEXER
    UPDATE -->|"git diff"| GIT

    %% Connexions Parsing
    INDEXER --> CTAGS
    INDEXER --> AST

    %% Relations internes DB
    SYMBOLS -.->|"FK"| FILES
    RELATIONS -.->|"FK"| SYMBOLS
    FILE_REL -.->|"FK"| FILES
    ERRORS -.->|"FK"| FILES
    ERRORS -.->|"FK"| SYMBOLS

    %% Styles
    classDef primary fill:#3b82f6,stroke:#1d4ed8,color:white
    classDef secondary fill:#8b5cf6,stroke:#6d28d9,color:white
    classDef database fill:#f59e0b,stroke:#d97706,color:white
    classDef script fill:#10b981,stroke:#059669,color:white
    classDef external fill:#6b7280,stroke:#4b5563,color:white

    class CLAUDE,SERVER primary
    class T1,T2,T3,T4,T5,T6,T7,T8,T9,T10 secondary
    class FILES,SYMBOLS,RELATIONS,FILE_REL,ERRORS,PIPELINE,SNAPSHOT,PATTERNS,ADR,CRITICAL database
    class BOOTSTRAP,UPDATE script
    class USER,GIT,IDE external
```

---

## Flux de Donnees Detaille

### Flux 1 : Bootstrap Initial

```mermaid
sequenceDiagram
    participant U as Utilisateur
    participant B as bootstrap.py
    participant I as indexer.py
    participant C as ctags/AST
    participant DB as SQLite
    participant G as Git

    U->>B: python bootstrap.py

    rect rgb(59, 130, 246, 0.1)
        Note over B: Etape 1-2: Initialisation
        B->>DB: CREATE TABLE (schema.sql)
        B->>DB: INSERT meta
    end

    rect rgb(139, 92, 246, 0.1)
        Note over B: Etape 3-4: Scan & Index
        B->>I: scan_project()
        loop Pour chaque fichier
            I->>C: parse(file)
            C-->>I: symbols[]
            I->>DB: INSERT files, symbols
        end
    end

    rect rgb(16, 185, 129, 0.1)
        Note over B: Etape 5-6: Metriques
        B->>I: calculate_metrics()
        B->>G: git log --stat
        G-->>B: commit history
        B->>DB: UPDATE files (metrics)
    end

    rect rgb(245, 158, 11, 0.1)
        Note over B: Etape 7-9: Finalisation
        B->>DB: Mark critical paths
        B->>DB: INSERT default patterns
        B->>DB: PRAGMA integrity_check
    end

    B-->>U: Database ready
```

---

### Flux 2 : Requete MCP

```mermaid
sequenceDiagram
    participant A as Agent IA
    participant S as MCP Server
    participant T as tools.py
    participant Q as queries.py
    participant DB as SQLite

    A->>S: get_file_context("src/lcd.c")
    S->>T: get_file_context(db, path)

    par Recuperation parallele
        T->>DB: SELECT * FROM files WHERE path=?
        T->>DB: SELECT * FROM symbols WHERE file_id=?
        T->>Q: get_file_dependencies()
        Q->>DB: Recursive CTE query
    end

    T->>T: Format JSON (PARTIE 7.2)
    T-->>S: {file, symbols, dependencies, ...}
    S-->>A: JSON Response
```

---

### Flux 3 : Mise a Jour Incrementale

```mermaid
sequenceDiagram
    participant U as Utilisateur
    participant UP as update.py
    participant G as Git
    participant I as indexer.py
    participant DB as SQLite

    U->>UP: python update.py
    UP->>G: git diff --name-status
    G-->>UP: [modified_files]

    loop Pour chaque fichier modifie
        UP->>DB: DELETE FROM symbols WHERE file_id=?
        UP->>I: index_file(path)
        I->>DB: INSERT symbols, relations
    end

    UP->>G: git log (activity)
    UP->>DB: UPDATE files (commits_30d, ...)
    UP-->>U: Updated in <5s
```

---

## Schema de la Base de Donnees

```mermaid
erDiagram
    FILES ||--o{ SYMBOLS : contains
    FILES ||--o{ FILE_RELATIONS : source
    FILES ||--o{ FILE_RELATIONS : target
    SYMBOLS ||--o{ RELATIONS : source
    SYMBOLS ||--o{ RELATIONS : target
    FILES ||--o{ ERROR_HISTORY : has
    SYMBOLS ||--o{ ERROR_HISTORY : affects

    FILES {
        int id PK
        text path UK
        text module
        text language
        bool is_critical
        int lines_code
        real complexity_avg
        int commits_30d
        text content_hash
    }

    SYMBOLS {
        int id PK
        int file_id FK
        text name
        text kind
        text signature
        int line_start
        int complexity
        bool has_doc
    }

    RELATIONS {
        int id PK
        int source_id FK
        int target_id FK
        text relation_type
        int count
        bool is_direct
    }

    FILE_RELATIONS {
        int id PK
        int source_file_id FK
        int target_file_id FK
        text relation_type
    }

    ERROR_HISTORY {
        int id PK
        int file_id FK
        text error_type
        text severity
        text title
        text resolution
        text discovered_at
        bool is_regression
    }

    PATTERNS {
        int id PK
        text name UK
        text category
        text description
        text good_example
        text bad_example
        text severity
    }

    ARCHITECTURE_DECISIONS {
        int id PK
        text decision_id UK
        text status
        text title
        text decision
        text consequences
    }

    PIPELINE_RUNS {
        int id PK
        text run_id UK
        text commit_hash
        text status
        int overall_score
        text issues_json
    }
```

---

## Hierarchie des Composants

```mermaid
graph TD
    subgraph "Niveau 3: Interface"
        MCP["MCP Server"]
        CLI["Scripts CLI"]
    end

    subgraph "Niveau 2: Logique Metier"
        TOOLS["tools.py<br/>10 Outils"]
        QUERIES["queries.py<br/>Graphe"]
        INDEXER["indexer.py<br/>Parsing"]
    end

    subgraph "Niveau 1: Acces Donnees"
        CRUD["crud.py<br/>Repositories"]
        MODELS["models.py<br/>Dataclasses"]
        CONFIG["config.py<br/>YAML Parser"]
    end

    subgraph "Niveau 0: Persistence"
        DB["db.py<br/>SQLite Manager"]
        SQLITE[("db.sqlite")]
    end

    MCP --> TOOLS
    CLI --> INDEXER
    CLI --> QUERIES

    TOOLS --> QUERIES
    TOOLS --> CRUD
    QUERIES --> CRUD
    INDEXER --> CRUD
    INDEXER --> CONFIG

    CRUD --> MODELS
    CRUD --> DB

    DB --> SQLITE
```

---

## Types de Relations du Graphe

```mermaid
graph LR
    subgraph "Relations Symbole-Symbole"
        A[function_a] -->|calls| B[function_b]
        C[struct_x] -->|inherits| D[struct_y]
        E[func] -->|uses_type| F[type_t]
        G[func] -->|returns_type| H[type_r]
    end

    subgraph "Relations Fichier-Fichier"
        I[main.c] -->|includes| J[header.h]
        K[module.py] -->|imports| L[utils.py]
    end
```

**Types de relations supportes** :

| Categorie | Types |
|-----------|-------|
| Appels | `calls`, `uses_variable`, `modifies`, `reads` |
| Inclusion | `includes`, `imports` |
| Types | `uses_type`, `returns_type`, `has_param_type` |
| Heritage | `inherits`, `implements` |
| Structure | `contains`, `defines`, `declares` |
| Autres | `instantiates`, `uses_macro`, `references` |

---

## Caracteristiques de Performance

| Operation | Temps Cible | Strategie |
|-----------|-------------|-----------|
| Bootstrap petit projet (100 fichiers) | ~10s | Indexation parallele |
| Bootstrap moyen (1000 fichiers) | ~2min | Batch inserts |
| Mise a jour incrementale | <5s | Delta detection |
| Requete simple | <10ms | Index SQL |
| Traversee graphe (depth 3) | 50-200ms | CTE recursives |
| Analyse d'impact complete | 100-500ms | Cache + index |

---

## Configuration SQLite Optimisee

```sql
PRAGMA foreign_keys = ON;      -- Integrite referentielle
PRAGMA journal_mode = WAL;     -- Write-Ahead Logging
PRAGMA synchronous = NORMAL;   -- Performance vs durabilite
PRAGMA cache_size = -64000;    -- 64MB cache
PRAGMA temp_store = MEMORY;    -- Temp tables en RAM
```

---

## Prochaine Etape

Continuez vers [03-analyse-configuration.md](./03-analyse-configuration.md) pour une dissection complete des fichiers de configuration.
