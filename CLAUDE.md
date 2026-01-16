# CLAUDE.md - CRE Flow

## Vue d'ensemble

**CRE Flow** (Code Review Engine) est un système d'analyse de code multi-agents avec base de données sémantique. Il orchestre 8 agents spécialisés pour produire des rapports de code review automatisés, compatibles avec une interface web.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PHASE 1 : PARALLÈLE                       │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐                    │
│   │ ANALYZER │   │ SECURITY │   │ REVIEWER │                    │
│   └────┬─────┘   └────┬─────┘   └────┬─────┘                    │
│        └──────────────┼──────────────┘                          │
│                       ▼                                          │
├─────────────────────────────────────────────────────────────────┤
│                     PHASE 2 : RISK puis PARALLÈLE               │
│                 ┌──────────┐                                     │
│                 │   RISK   │                                     │
│                 └────┬─────┘                                     │
│        ┌─────────────┴─────────────┐                             │
│   ┌────┴─────┐               ┌─────┴────┐                        │
│   │SYNTHESIS │               │  SONAR   │ (si SonarCloud dispo)  │
│   └────┬─────┘               └────┬─────┘                        │
│        └──────────┬───────────────┘                              │
├─────────────────────────────────────────────────────────────────┤
│                     PHASE 3 : META-SYNTHESIS                     │
├─────────────────────────────────────────────────────────────────┤
│                     PHASE 4 : WEB-SYNTHESIZER                    │
│                              ▼                                   │
│               reports/web-report-{date}-{commit}.json            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Structure du projet

```
flow/
├── main.py                      # API FastAPI (déclencheur d'analyses)
├── claude.py                    # WebSocket notifier & Claude launcher
├── .env.example                 # Template configuration
├── mkdocs.yml                   # Documentation MkDocs
│
├── .claude/
│   ├── agents/                  # 8 agents spécialisés
│   │   ├── analyzer.md          # Analyse d'impact et dépendances
│   │   ├── security.md          # Détection vulnérabilités (CWE)
│   │   ├── reviewer.md          # Qualité et conventions
│   │   ├── risk.md              # Évaluation du risque global
│   │   ├── synthesis.md         # Fusion des 4 agents
│   │   ├── sonar.md             # Enrichissement SonarCloud
│   │   ├── meta-synthesis.md    # Fusion SYNTHESIS + SONAR
│   │   └── web-synthesizer.md   # Export JSON pour site web
│   │
│   ├── agentdb/                 # Base de données sémantique
│   │   ├── db.py                # Connexion SQLite
│   │   ├── models.py            # Modèles de données
│   │   ├── crud.py              # Opérations CRUD
│   │   ├── queries.py           # Requêtes complexes
│   │   ├── indexer.py           # Indexation du code
│   │   ├── tree_sitter_parser.py # Parsing multi-langage
│   │   ├── query.sh             # CLI pour agents
│   │   ├── schema.sql           # Schéma DB
│   │   ├── db.sqlite            # Base principale
│   │   └── requirements.txt     # Dépendances Python
│   │
│   ├── commands/                # Commandes Claude
│   │   ├── analyze.md           # /analyze - Orchestrateur principal
│   │   └── analyze_py.md        # Variantes Python
│   │
│   ├── config/
│   │   ├── agentdb.yaml         # Config AgentDB complète
│   │   └── sonar.yaml           # Config SonarCloud
│   │
│   ├── scripts/
│   │   ├── bootstrap.py         # Initialisation DB
│   │   ├── transform-sonar.py   # Transformation rapport SonarCloud
│   │   ├── validate-web-report.py # Validation JSON final
│   │   └── maintenance.py       # Maintenance DB
│   │
│   ├── reports/                 # Rapports historiques
│   ├── sonar/                   # Issues SonarCloud (issues.json)
│   ├── logs/                    # Logs d'analyse
│   ├── tests/                   # Tests unitaires
│   └── worktree.py              # Gestion git worktrees
│
├── src/                         # Code source C (test codebase)
├── docs/                        # Documentation utilisateur
├── docs_claude/                 # Documentation agents
└── reports/                     # Rapports web (sortie finale)
```

---

## Installation

### Prérequis

- Python 3.10+
- SQLite 3
- Universal Ctags
- Git

### 1. Configuration environnement

```bash
cp .env.example .env
# Éditer .env avec vos credentials SonarCloud (optionnel)
```

### 2. Dépendances AgentDB

```bash
pip install -r .claude/agentdb/requirements.txt
```

Contenu des dépendances :
- **Parsing** : tree-sitter + grammaires (Python, C, C++, JS, TS, Go, Rust, Java)
- **Embeddings** : numpy, sentence-transformers
- **Config** : pyyaml

### 3. Dépendances Backend (pour main.py)

```bash
pip install fastapi websockets aiohttp pydantic python-dotenv
```

### 4. Initialisation de la base AgentDB

```bash
# Initialisation complète (premier usage)
python .claude/scripts/bootstrap.py --full

# Mise à jour incrémentale (après modifications)
python .claude/scripts/bootstrap.py --incremental
```

---

## Commandes

### Analyse de code

| Commande | Description |
|----------|-------------|
| `/analyze` | Lance une analyse complète avec les 8 agents |
| `python .claude/scripts/bootstrap.py --full` | Réinitialise AgentDB |
| `python .claude/scripts/bootstrap.py --incremental` | Met à jour AgentDB |

### API FastAPI

```bash
# Démarrer le serveur
uvicorn main:app --reload --port 8000
```

| Endpoint | Description |
|----------|-------------|
| `POST /trigger` | Déclenche une analyse |
| `GET /jobs/{id}` | Statut d'un job |
| `GET /admin/worktrees` | Liste les worktrees |
| `POST /admin/worktrees/cleanup` | Nettoie les worktrees expirés |

---

## AgentDB

### Commandes query.sh

Toujours utiliser `AGENTDB_CALLER` pour l'identification :

```bash
export AGENTDB_CALLER="analyzer"

# Contexte fichier
bash .claude/agentdb/query.sh file_context "path/to/file.cpp"

# Métriques fichier
bash .claude/agentdb/query.sh file_metrics "path/to/file.cpp"

# Impact modification
bash .claude/agentdb/query.sh file_impact "path/to/file.cpp"

# Appelants d'un symbole
bash .claude/agentdb/query.sh symbol_callers "functionName"

# Appelés par un symbole
bash .claude/agentdb/query.sh symbol_callees "functionName"

# Historique erreurs (90 derniers jours)
bash .claude/agentdb/query.sh error_history "path/to/file.cpp" 90

# Patterns de code
bash .claude/agentdb/query.sh patterns "path/to/file.cpp" "security"

# Décisions d'architecture (ADRs)
bash .claude/agentdb/query.sh architecture_decisions

# Recherche symboles
bash .claude/agentdb/query.sh search_symbols "UDP*" function

# Liste modules
bash .claude/agentdb/query.sh list_modules

# Fichiers critiques
bash .claude/agentdb/query.sh list_critical_files
```

### Commandes d'analyse incrémentale

```bash
# Checkpoints
bash .claude/agentdb/query.sh get_checkpoint "feature/my-branch"
bash .claude/agentdb/query.sh set_checkpoint "feature/my-branch" "abc123" 5 "APPROVE" 85
bash .claude/agentdb/query.sh reset_checkpoint "feature/my-branch"
bash .claude/agentdb/query.sh list_checkpoints

# Pipeline runs
bash .claude/agentdb/query.sh record_pipeline_run "branch" "commit" 75 "REVIEW" 10
bash .claude/agentdb/query.sh list_pipeline_runs 20
```

### Structure de la base (3 piliers)

1. **Graphe de dépendances** : files, symbols, relations, file_relations
2. **Mémoire historique** : error_history, pipeline_runs, snapshot_symbols
3. **Base de connaissances** : patterns, architecture_decisions, critical_paths

---

## Agents

### Phase 1 (Parallèle)

| Agent | Fichier | Rôle | Queries AgentDB |
|-------|---------|------|-----------------|
| ANALYZER | `analyzer.md` | Impact et dépendances | file_context, symbol_callers, file_impact |
| SECURITY | `security.md` | Vulnérabilités CWE | error_history, patterns (security) |
| REVIEWER | `reviewer.md` | Qualité et conventions | patterns, file_metrics, architecture_decisions |

### Phase 2

| Agent | Fichier | Rôle |
|-------|---------|------|
| RISK | `risk.md` | Calcul score de risque |
| SYNTHESIS | `synthesis.md` | Fusion des 4 agents |
| SONAR | `sonar.md` | Enrichissement issues SonarCloud |

### Phase 3-4

| Agent | Fichier | Rôle |
|-------|---------|------|
| META-SYNTHESIS | `meta-synthesis.md` | Fusion et dédoublonnage |
| WEB-SYNTHESIZER | `web-synthesizer.md` | Export JSON pour site web |

---

## Configuration

### Variables d'environnement (.env)

```bash
# SonarCloud (optionnel)
SONAR_TOKEN=your_token
SONAR_PROJECT_KEY=org_repo

# WebSocket (optionnel)
CRE_WS_URL=ws://localhost:3001
CRE_HTTP_URL=http://localhost:3001

# Mode test
TEST_MODE=0
```

### agentdb.yaml

Sections principales :
- `project` : Nom, langage principal, racine
- `database` : Chemin SQLite, WAL mode, cache
- `indexing` : Extensions, exclusions, outils par langage
- `criticality` : Chemins critiques, fichiers sensibles
- `metrics` : Seuils de complexité, documentation
- `git` : Fenêtres d'activité (30/90/365 jours)
- `analysis` : Poids des agents, seuils de verdict

---

## Verdicts

| Score | Verdict | Signification |
|-------|---------|---------------|
| ≥80 | APPROVE | Peut être mergé |
| ≥60 | REVIEW | Review humaine recommandée |
| ≥40 | CAREFUL | Review approfondie requise |
| <40 | REJECT | Ne pas merger |

### Formule de calcul

```
Score = Security × 0.35 + Risk × 0.25 + Reviewer × 0.25 + Analyzer × 0.15
```

---

## Règles de développement

### Agents

- **TOUJOURS** utiliser `AGENTDB_CALLER` dans les appels query.sh
- Ne jamais modifier les agents sans tester
- Chaque agent DOIT consulter AgentDB AVANT toute analyse
- Si AgentDB échoue, continuer avec grep/git comme fallback

### Code

- Utiliser les worktrees pour l'isolation des analyses
- Les rapports vont dans `.claude/reports/{date}-{commit}/`
- Le rapport web final va dans `reports/web-report-{date}-{commit}.json`

### LSP

- Travail sur fichier unique : laisser les diagnostics arriver via Read/Edit
- Audit/scan projet : utiliser `LSP(documentSymbol)`
- Navigation : `LSP(goToDefinition)`, `LSP(findReferences)`, `LSP(hover)`
- Toujours vérifier les `<new-diagnostics>` dans les résultats

---

## Langages supportés

| Langage | Extensions | Outil d'indexation |
|---------|------------|-------------------|
| C | .c, .h | ctags |
| C++ | .cpp, .hpp, .cc, .hh | ctags |
| Python | .py, .pyi | AST |
| JavaScript | .js, .jsx, .mjs | ctags |
| TypeScript | .ts, .tsx | ctags |
| Go | .go | ctags |
| Rust | .rs | ctags |
| Java | .java | ctags |

---

## Dépannage

### AgentDB vide ou erreurs

```bash
# Réinitialiser complètement
rm .claude/agentdb/db.sqlite
python .claude/scripts/bootstrap.py --full
```

### Worktrees bloqués

```bash
# Lister les worktrees
git worktree list

# Nettoyer via API
curl -X POST http://localhost:8000/admin/worktrees/cleanup

# Ou manuellement
git worktree remove /path/to/worktree --force
```

### Logs d'analyse

```bash
# Voir les dernières requêtes AgentDB
tail -f .claude/logs/agentdb_queries.log
```
