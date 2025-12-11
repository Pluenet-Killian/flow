# Analyse de Configuration

> Dissection complete des fichiers de configuration du systeme AgentDB

---

## Vue d'Ensemble des Fichiers de Configuration

| Fichier | Role | Format |
|---------|------|--------|
| `.claude/settings.json` | Configuration du serveur MCP | JSON |
| `.claude/config/agentdb.yaml` | Configuration complete d'AgentDB | YAML |

---

## 1. Configuration MCP : `settings.json`

Ce fichier configure l'integration de Claude Code avec le serveur MCP d'AgentDB.

### Contenu Complet

```json
{
  "mcpServers": {
    "agentdb": {
      "command": "python",
      "args": ["-m", "mcp.agentdb.server"],
      "cwd": "${workspaceFolder}/.claude",
      "env": {
        "AGENTDB_PATH": "${workspaceFolder}/.claude/agentdb/db.sqlite",
        "AGENTDB_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Analyse Ligne par Ligne

| Cle | Valeur | Description |
|-----|--------|-------------|
| `mcpServers` | Object | Conteneur pour tous les serveurs MCP |
| `agentdb` | Object | Identifiant unique du serveur AgentDB |
| `command` | `"python"` | Executeur Python pour lancer le serveur |
| `args` | `["-m", "mcp.agentdb.server"]` | Lance le module `mcp.agentdb.server` |
| `cwd` | `"${workspaceFolder}/.claude"` | Repertoire de travail (dossier .claude) |
| `env.AGENTDB_PATH` | Chemin base | Localisation du fichier SQLite |
| `env.AGENTDB_LOG_LEVEL` | `"INFO"` | Niveau de log (DEBUG, INFO, WARNING, ERROR) |

### Variables Dynamiques

| Variable | Resolution |
|----------|------------|
| `${workspaceFolder}` | Racine du projet ouvert |

---

## 2. Configuration AgentDB : `agentdb.yaml`

Ce fichier YAML controle l'ensemble du comportement d'AgentDB.

---

### Section : Project

```yaml
project:
  name: "flow"
  description: "Multi-agent code review system"
  version: "1.0.0"
  language: "c"
  root: "."
```

| Parametre | Type | Description |
|-----------|------|-------------|
| `name` | string | Nom du projet indexe |
| `description` | string | Description pour les rapports |
| `version` | string | Version du projet |
| `language` | enum | Langage principal (`c`, `cpp`, `python`, `javascript`) |
| `root` | path | Racine relative du projet |

---

### Section : Database

```yaml
database:
  path: ".claude/agentdb/db.sqlite"
  wal_mode: true
  timeout: 30
  cache_size: 10000
```

| Parametre | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | path | `.claude/agentdb/db.sqlite` | Chemin vers la base SQLite |
| `wal_mode` | bool | `true` | Active le mode WAL (Write-Ahead Logging) |
| `timeout` | int | `30` | Timeout des requetes en secondes |
| `cache_size` | int | `10000` | Taille du cache en pages (1 page = 4KB) |

> **Note WAL** : Le mode WAL permet des lectures concurrentes pendant les ecritures, ideal pour un serveur MCP.

---

### Section : Indexing

```yaml
indexing:
  extensions:
    c: [".c", ".h"]
    cpp: [".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx"]
    python: [".py", ".pyi"]
    javascript: [".js", ".jsx", ".mjs"]
    typescript: [".ts", ".tsx"]
    rust: [".rs"]
    go: [".go"]

  exclude:
    # Build artifacts
    - "build/**"
    - "dist/**"
    - "*.o"
    - "*.exe"

    # Dependencies
    - "vendor/**"
    - "node_modules/**"
    - ".venv/**"
    - "__pycache__/**"

    # IDE and VCS
    - ".git/**"
    - ".idea/**"
    - ".vscode/**"

    # Generated
    - "**/*.min.js"
    - "**/generated/**"

    # AgentDB internal
    - ".claude/agentdb/**"

  tools:
    c: "ctags"
    cpp: "ctags"
    python: "ast"
    javascript: "ctags"
    typescript: "ctags"
    rust: "ctags"
    go: "ctags"

  max_file_size: 1048576  # 1 MB
  parallel_workers: 4
  file_timeout: 30
```

#### Sous-section : Extensions

Association langage -> extensions de fichiers :

| Langage | Extensions Indexees |
|---------|---------------------|
| C | `.c`, `.h` |
| C++ | `.cpp`, `.hpp`, `.cc`, `.hh`, `.cxx`, `.hxx` |
| Python | `.py`, `.pyi` |
| JavaScript | `.js`, `.jsx`, `.mjs` |
| TypeScript | `.ts`, `.tsx` |
| Rust | `.rs` |
| Go | `.go` |

#### Sous-section : Exclude

Patterns glob pour exclure des fichiers :

| Categorie | Patterns | Raison |
|-----------|----------|--------|
| Build | `build/**`, `dist/**`, `*.o` | Fichiers generes |
| Deps | `node_modules/**`, `.venv/**` | Dependances externes |
| VCS | `.git/**` | Historique Git |
| IDE | `.idea/**`, `.vscode/**` | Configuration IDE |
| Generated | `**/*.min.js`, `**/generated/**` | Code genere |
| Internal | `.claude/agentdb/**` | Eviter auto-reference |

#### Sous-section : Tools

Outil de parsing par langage :

| Outil | Langages | Description |
|-------|----------|-------------|
| `ctags` | C, C++, JS, TS, Rust, Go | Universal Ctags (externe) |
| `ast` | Python | Module `ast` Python natif |

#### Parametres de Performance

| Parametre | Valeur | Description |
|-----------|--------|-------------|
| `max_file_size` | 1MB | Fichiers plus gros sont ignores |
| `parallel_workers` | 4 | Threads de parsing paralleles |
| `file_timeout` | 30s | Timeout par fichier |

---

### Section : Criticality

```yaml
criticality:
  critical_paths:
    # Securite
    - "**/security/**"
    - "**/auth/**"
    - "**/crypto/**"

    # Donnees sensibles
    - "**/*password*"
    - "**/*secret*"
    - "**/*token*"

    # Points d'entree
    - "**/main.*"
    - "**/init.*"
    - "**/bootstrap.*"

    # Base de donnees
    - "**/migration*"
    - "**/schema*"

  high_importance_paths:
    - "**/core/**"
    - "**/api/**"
    - "**/services/**"
    - "**/models/**"

  sensitive_content_patterns:
    - "AES"
    - "RSA"
    - "bcrypt"
    - "password"
    - "api_key"
    - "access_token"
```

#### Detection de Criticite

Les fichiers sont marques comme **critiques** selon ces criteres :

| Critere | Patterns | Impact |
|---------|----------|--------|
| Chemins securite | `**/security/**`, `**/auth/**` | `is_critical = true` |
| Noms sensibles | `*password*`, `*secret*` | `is_critical = true` |
| Points d'entree | `**/main.*`, `**/init.*` | `is_critical = true` |
| Contenu sensible | Presence de "AES", "bcrypt" | `security_sensitive = true` |

---

### Section : Metrics

```yaml
metrics:
  complexity:
    low: 5
    medium: 10
    high: 20
    critical: 30

  documentation:
    min_public_documented: 80
    min_classes_documented: 90
    min_docstring_length: 10

  function_length:
    ideal: 30
    warning: 50
    error: 100
    critical: 200

  file_length:
    ideal: 300
    warning: 500
    error: 1000
    critical: 2000

  nesting_depth:
    ideal: 3
    warning: 5
    critical: 7

  comment_ratio:
    min: 0.1
    ideal: 0.2
    max: 0.5
```

#### Seuils de Complexite Cyclomatique

```
     Complexite
         ^
    30 --+---------------------- CRITIQUE (refactoring requis)
         |  Zone Rouge
    20 --+---------------------- HIGH (warning severe)
         |  Zone Orange
    10 --+---------------------- MEDIUM (attention)
         |  Zone Jaune
     5 --+---------------------- LOW (acceptable)
         |  Zone Verte
     0 --+----------------------
```

#### Seuils de Longueur

| Metrique | Ideal | Warning | Error | Critique |
|----------|-------|---------|-------|----------|
| Fonction (lignes) | 30 | 50 | 100 | 200 |
| Fichier (lignes) | 300 | 500 | 1000 | 2000 |
| Imbrication | 3 | 5 | - | 7 |

---

### Section : Git

```yaml
git:
  activity_periods:
    recent: 30
    short_term: 90
    long_term: 365

  hot_file_thresholds:
    recent_commits: 5
    short_term_commits: 15

  ignore_authors:
    - "dependabot[bot]"
    - "renovate[bot]"
    - "github-actions[bot]"

  analyze_blame: true
  ignore_merge_commits: true
  max_commits_per_file: 100
```

#### Detection des "Hot Files"

Un fichier est considere "hot" (instable) si :

| Periode | Seuil | Signification |
|---------|-------|---------------|
| 30 jours | >= 5 commits | Changements frequents recents |
| 90 jours | >= 15 commits | Activite soutenue |

> **Warning** : Les hot files sont des indicateurs de dette technique potentielle.

---

### Section : Patterns

```yaml
patterns:
  enabled_categories:
    - "error_handling"
    - "memory_safety"
    - "naming_convention"
    - "documentation"
    - "security"
    - "performance"

  default_severity: "warning"
  custom: []
```

#### Categories de Patterns

| Categorie | Description | Exemple |
|-----------|-------------|---------|
| `error_handling` | Gestion des erreurs | Toujours verifier les retours |
| `memory_safety` | Securite memoire | Free apres malloc |
| `naming_convention` | Conventions de nommage | snake_case pour C |
| `documentation` | Documentation | Fonctions publiques documentees |
| `security` | Securite | Valider toutes les entrees |
| `performance` | Performance | Eviter O(n^2) dans les hot paths |

---

### Section : MCP

```yaml
mcp:
  mode: "stdio"
  log_level: "INFO"
  request_timeout: 30
  cache_ttl: 60
```

| Parametre | Valeur | Description |
|-----------|--------|-------------|
| `mode` | `stdio` | Communication via stdin/stdout |
| `log_level` | `INFO` | Niveau de journalisation |
| `request_timeout` | 30s | Timeout des requetes MCP |
| `cache_ttl` | 60s | Duree de vie du cache |

> **Note** : Le mode `tcp` (avec `port`) est supporte mais non utilise par defaut.

---

### Section : Maintenance

```yaml
maintenance:
  snapshot_retention_days: 30
  keep_detailed_runs: 100
  auto_vacuum_threshold: 1000
```

| Parametre | Valeur | Description |
|-----------|--------|-------------|
| `snapshot_retention_days` | 30 | Jours de retention des snapshots |
| `keep_detailed_runs` | 100 | Nombre de runs pipeline a conserver |
| `auto_vacuum_threshold` | 1000 | Vacuum apres N suppressions |

---

### Section : Logging

```yaml
logging:
  directory: ".claude/logs"
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  max_size_mb: 10
  backup_count: 5
```

#### Format de Log

```
2024-01-15 10:30:45 - agentdb.indexer - INFO - Indexed 150 files
```

| Composant | Description |
|-----------|-------------|
| `asctime` | Timestamp ISO |
| `name` | Nom du logger |
| `levelname` | Niveau (DEBUG, INFO, WARNING, ERROR) |
| `message` | Message |

---

## Variables d'Environnement Supportees

Le fichier YAML supporte les variables d'environnement :

```yaml
database:
  path: "${PROJECT_ROOT}/.claude/agentdb/db.sqlite"
```

| Variable | Description |
|----------|-------------|
| `${PROJECT_ROOT}` | Racine du projet |
| `${HOME}` | Repertoire home utilisateur |
| `${VAR:-default}` | Valeur par defaut si VAR non definie |

---

## Validation de la Configuration

AgentDB valide la configuration au demarrage :

```python
# Validation automatique
config = Config.load("config/agentdb.yaml")
errors = config.validate()

if errors:
    for error in errors:
        print(f"Config error: {error}")
```

### Erreurs Courantes

| Erreur | Cause | Solution |
|--------|-------|----------|
| `Invalid path` | Chemin database invalide | Verifier le chemin |
| `Unknown language` | Langage non supporte | Utiliser c, cpp, python, js, ts |
| `Invalid glob pattern` | Pattern exclude malformed | Verifier la syntaxe glob |

---

## Prochaine Etape

Continuez vers [04-mcp-et-outils.md](./04-mcp-et-outils.md) pour la documentation technique des 10 outils MCP.
