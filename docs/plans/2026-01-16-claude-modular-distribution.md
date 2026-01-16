# .claude Modular Distribution - Plan d'Implémentation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Permettre la distribution de `.claude` sur plusieurs projets tout en maintenant des AgentDB uniques par projet et la propagation automatique des mises à jour.

**Architecture:** Git submodule pour le code partagé + structure locale pour les données projet-spécifiques. Le `.claude` original devient un dépôt Git séparé, les projets l'incluent comme submodule et génèrent leurs propres données.

**Tech Stack:** Git submodules, Bash scripts, Python (bootstrap), symlinks

---

## Analyse de la Séparation

### Composants PARTAGÉS (à mettre dans le submodule)
```
.claude-shared/
├── agentdb/
│   ├── *.py              # Librairie Python (11 modules)
│   ├── schema.sql        # Schéma de base
│   ├── query.sh          # Interface requêtes
│   └── requirements.txt  # Dépendances
├── agents/               # 7 agents d'analyse
├── commands/             # Commandes (/analyze, etc.)
├── mcp/                  # Serveur MCP
├── scripts/              # Bootstrap, maintenance
└── tests/                # Tests unitaires
```

### Composants PROJET-SPÉCIFIQUES (restent locaux)
```
.claude/
├── data/
│   ├── db.sqlite         # Base de données unique
│   ├── shared.sqlite     # Checkpoints
│   └── *.sqlite.bak      # Backups
├── config/
│   ├── agentdb.yaml      # Config projet
│   └── sonar.yaml        # Credentials SonarCloud
├── reports/              # Historique analyses
├── logs/                 # Logs runtime
└── sonar/                # Issues SonarCloud
```

---

## Task 1: Créer le dépôt partagé `.claude-shared`

**Files:**
- Create: `~/.claude-shared/` (nouveau dépôt Git)
- Copy from: `.claude/agentdb/*.py`, `.claude/agents/`, etc.

**Step 1: Créer la structure du dépôt partagé**

```bash
mkdir -p ~/.claude-shared
cd ~/.claude-shared
git init
```

**Step 2: Copier les composants partagés**

```bash
# Depuis le projet flow
cd /home/simia/dev/corpo/cre/flow

# AgentDB code (pas les .sqlite)
mkdir -p ~/.claude-shared/agentdb
cp .claude/agentdb/*.py ~/.claude-shared/agentdb/
cp .claude/agentdb/schema.sql ~/.claude-shared/agentdb/
cp .claude/agentdb/query.sh ~/.claude-shared/agentdb/
cp .claude/agentdb/requirements.txt ~/.claude-shared/agentdb/

# Agents
cp -r .claude/agents ~/.claude-shared/

# Commands
cp -r .claude/commands ~/.claude-shared/

# MCP
cp -r .claude/mcp ~/.claude-shared/

# Scripts
cp -r .claude/scripts ~/.claude-shared/

# Tests
cp -r .claude/tests ~/.claude-shared/
```

**Step 3: Commit initial**

```bash
cd ~/.claude-shared
git add .
git commit -m "feat: initial shared .claude components"
```

---

## Task 2: Créer le script d'installation `install.sh`

**Files:**
- Create: `~/.claude-shared/install.sh`

**Step 1: Écrire le script d'installation**

```bash
#!/bin/bash
# install.sh - Installe .claude dans un projet cible
# Usage: ./install.sh [project-path]

set -e

PROJECT_ROOT="${1:-.}"
CLAUDE_SHARED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installation de .claude-shared ==="
echo "Projet cible: $PROJECT_ROOT"
echo "Source partagée: $CLAUDE_SHARED_DIR"

# Créer la structure locale
mkdir -p "$PROJECT_ROOT/.claude/data"
mkdir -p "$PROJECT_ROOT/.claude/config"
mkdir -p "$PROJECT_ROOT/.claude/reports"
mkdir -p "$PROJECT_ROOT/.claude/logs"
mkdir -p "$PROJECT_ROOT/.claude/sonar"

# Créer les symlinks vers les composants partagés
ln -sfn "$CLAUDE_SHARED_DIR/agentdb" "$PROJECT_ROOT/.claude/agentdb"
ln -sfn "$CLAUDE_SHARED_DIR/agents" "$PROJECT_ROOT/.claude/agents"
ln -sfn "$CLAUDE_SHARED_DIR/commands" "$PROJECT_ROOT/.claude/commands"
ln -sfn "$CLAUDE_SHARED_DIR/mcp" "$PROJECT_ROOT/.claude/mcp"
ln -sfn "$CLAUDE_SHARED_DIR/scripts" "$PROJECT_ROOT/.claude/scripts"
ln -sfn "$CLAUDE_SHARED_DIR/tests" "$PROJECT_ROOT/.claude/tests"

# Créer le fichier de config template si absent
if [ ! -f "$PROJECT_ROOT/.claude/config/agentdb.yaml" ]; then
    cat > "$PROJECT_ROOT/.claude/config/agentdb.yaml" << 'EOF'
# Configuration AgentDB - Projet spécifique
# Généré par install.sh

project:
  name: "my-project"  # À personnaliser
  language: "python"  # À personnaliser
  root: "."

database:
  path: ".claude/data/db.sqlite"
  wal_mode: true

indexing:
  extensions:
    python: [".py"]
    javascript: [".js", ".jsx"]
    typescript: [".ts", ".tsx"]
  exclude:
    - "build/**"
    - "dist/**"
    - ".git/**"
    - ".claude/data/**"
    - "node_modules/**"
    - "__pycache__/**"
    - "*.pyc"
  max_file_size: 1048576
  parallel_workers: 4

criticality:
  critical_paths:
    - "**/security/**"
    - "**/auth/**"
    - "**/crypto/**"
  high_importance_paths:
    - "**/core/**"
    - "**/api/**"

logging:
  level: "INFO"
  directory: ".claude/logs"

reports:
  output_directory: ".claude/reports"
EOF
    echo "✓ Config template créée: .claude/config/agentdb.yaml"
fi

# Créer le wrapper pour query.sh qui utilise la bonne DB
cat > "$PROJECT_ROOT/.claude/query-local.sh" << 'EOF'
#!/bin/bash
# Wrapper local pour query.sh
# Redirige vers la DB du projet

export AGENTDB_PATH="${AGENTDB_PATH:-$(dirname "$0")/data/db.sqlite}"
exec "$(dirname "$0")/agentdb/query.sh" "$@"
EOF
chmod +x "$PROJECT_ROOT/.claude/query-local.sh"

echo ""
echo "=== Installation terminée ==="
echo ""
echo "Prochaines étapes:"
echo "  1. Éditer .claude/config/agentdb.yaml (nom projet, langage, etc.)"
echo "  2. Installer les dépendances: pip install -r .claude/agentdb/requirements.txt"
echo "  3. Initialiser la DB: python .claude/scripts/bootstrap.py --full"
echo ""
```

**Step 2: Rendre exécutable et commiter**

```bash
chmod +x ~/.claude-shared/install.sh
cd ~/.claude-shared
git add install.sh
git commit -m "feat: add install.sh for project setup"
```

---

## Task 3: Modifier `bootstrap.py` pour supporter les chemins flexibles

**Files:**
- Modify: `~/.claude-shared/scripts/bootstrap.py`

**Step 1: Identifier les chemins hardcodés dans bootstrap.py**

Les chemins à rendre configurables:
- Base de données: `.claude/agentdb/db.sqlite` → `.claude/data/db.sqlite`
- Config: `.claude/config/agentdb.yaml` (OK, déjà flexible)
- Logs: `.claude/logs/` (OK via config)

**Step 2: Modifier la résolution des chemins**

Ajouter en début de bootstrap.py:

```python
def get_data_path(project_root: Path) -> Path:
    """Retourne le chemin vers les données (DB, logs, reports).

    Priorité:
    1. Variable d'env CLAUDE_DATA_DIR
    2. .claude/data/ si symlink détecté pour agentdb
    3. .claude/agentdb/ (fallback legacy)
    """
    if "CLAUDE_DATA_DIR" in os.environ:
        return Path(os.environ["CLAUDE_DATA_DIR"])

    agentdb_path = project_root / ".claude" / "agentdb"
    if agentdb_path.is_symlink():
        # Structure modulaire: data séparé
        return project_root / ".claude" / "data"
    else:
        # Structure legacy: tout dans agentdb
        return project_root / ".claude" / "agentdb"
```

**Step 3: Utiliser get_data_path() dans bootstrap**

Remplacer les références à `.claude/agentdb/db.sqlite` par:

```python
data_dir = get_data_path(project_root)
db_path = data_dir / "db.sqlite"
```

**Step 4: Commit**

```bash
cd ~/.claude-shared
git add scripts/bootstrap.py
git commit -m "feat: support flexible data paths for modular install"
```

---

## Task 4: Modifier `query.sh` pour auto-détecter la DB

**Files:**
- Modify: `~/.claude-shared/agentdb/query.sh`

**Step 1: Ajouter la détection automatique**

En début de query.sh, après les imports:

```bash
# Auto-détection du chemin DB
if [ -z "$AGENTDB_PATH" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    CLAUDE_DIR="$(dirname "$SCRIPT_DIR")"

    # Structure modulaire ?
    if [ -L "$SCRIPT_DIR" ]; then
        # Symlink détecté: chercher data/db.sqlite dans le projet
        # Remonter jusqu'à trouver .claude/data/
        SEARCH_DIR="$PWD"
        while [ "$SEARCH_DIR" != "/" ]; do
            if [ -f "$SEARCH_DIR/.claude/data/db.sqlite" ]; then
                AGENTDB_PATH="$SEARCH_DIR/.claude/data/db.sqlite"
                break
            fi
            SEARCH_DIR="$(dirname "$SEARCH_DIR")"
        done
    fi

    # Fallback: structure legacy
    if [ -z "$AGENTDB_PATH" ] && [ -f "$CLAUDE_DIR/agentdb/db.sqlite" ]; then
        AGENTDB_PATH="$CLAUDE_DIR/agentdb/db.sqlite"
    fi

    # Dernier fallback
    if [ -z "$AGENTDB_PATH" ]; then
        AGENTDB_PATH=".claude/data/db.sqlite"
    fi
fi

export AGENTDB_PATH
```

**Step 2: Commit**

```bash
cd ~/.claude-shared
git add agentdb/query.sh
git commit -m "feat: auto-detect database path in query.sh"
```

---

## Task 5: Modifier le serveur MCP pour les chemins flexibles

**Files:**
- Modify: `~/.claude-shared/mcp/agentdb/server.py`

**Step 1: Ajouter la détection de structure**

Dans server.py, modifier l'initialisation:

```python
def get_db_path() -> Path:
    """Retourne le chemin DB en détectant la structure."""
    # 1. Variable d'environnement explicite
    if "AGENTDB_PATH" in os.environ:
        return Path(os.environ["AGENTDB_PATH"])

    # 2. Détection de la structure
    cwd = Path.cwd()

    # Structure modulaire
    data_path = cwd / ".claude" / "data" / "db.sqlite"
    if data_path.exists():
        return data_path

    # Structure legacy
    legacy_path = cwd / ".claude" / "agentdb" / "db.sqlite"
    if legacy_path.exists():
        return legacy_path

    # Default: structure modulaire
    return data_path
```

**Step 2: Commit**

```bash
cd ~/.claude-shared
git add mcp/agentdb/server.py
git commit -m "feat: flexible DB path detection in MCP server"
```

---

## Task 6: Créer le script de mise à jour `update-shared.sh`

**Files:**
- Create: `~/.claude-shared/update-shared.sh`

**Step 1: Écrire le script de mise à jour**

```bash
#!/bin/bash
# update-shared.sh - Met à jour .claude-shared depuis les sources
# Usage: ./update-shared.sh [source-project-path]

set -e

SOURCE_PROJECT="${1:-/home/simia/dev/corpo/cre/flow}"
SHARED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Mise à jour de .claude-shared ==="
echo "Source: $SOURCE_PROJECT/.claude"
echo "Destination: $SHARED_DIR"
echo ""

# Liste des composants à synchroniser
COMPONENTS=(
    "agentdb/*.py"
    "agentdb/schema.sql"
    "agentdb/query.sh"
    "agentdb/requirements.txt"
    "agents"
    "commands"
    "mcp"
    "scripts"
    "tests"
)

for component in "${COMPONENTS[@]}"; do
    src="$SOURCE_PROJECT/.claude/$component"

    if [[ "$component" == *"*"* ]]; then
        # Pattern avec wildcard
        dir=$(dirname "$component")
        mkdir -p "$SHARED_DIR/$dir"
        cp $src "$SHARED_DIR/$dir/" 2>/dev/null || true
    elif [ -d "$src" ]; then
        # Répertoire
        rsync -av --delete "$src/" "$SHARED_DIR/$component/"
    elif [ -f "$src" ]; then
        # Fichier unique
        cp "$src" "$SHARED_DIR/$component"
    fi
done

echo ""
echo "=== Synchronisation terminée ==="

# Afficher les changements
cd "$SHARED_DIR"
if [ -n "$(git status --porcelain)" ]; then
    echo ""
    echo "Changements détectés:"
    git status --short
    echo ""
    read -p "Commiter ces changements? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git add .
        git commit -m "sync: update from source project $(date +%Y-%m-%d)"
        echo "✓ Changements commités"
    fi
else
    echo "Aucun changement détecté."
fi
```

**Step 2: Commit**

```bash
chmod +x ~/.claude-shared/update-shared.sh
cd ~/.claude-shared
git add update-shared.sh
git commit -m "feat: add update-shared.sh for syncing from source"
```

---

## Task 7: Créer `.gitignore` pour le dépôt partagé

**Files:**
- Create: `~/.claude-shared/.gitignore`

**Step 1: Écrire le .gitignore**

```gitignore
# Données projet-spécifiques (ne doivent JAMAIS être dans le repo partagé)
*.sqlite
*.sqlite-wal
*.sqlite-shm
*.sqlite.bak

# Logs
logs/
*.log

# Reports
reports/

# Config avec secrets
config/sonar.yaml

# Cache Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/

# Environnements virtuels
venv/
.venv/
env/

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

**Step 2: Commit**

```bash
cd ~/.claude-shared
git add .gitignore
git commit -m "chore: add .gitignore for shared repo"
```

---

## Task 8: Créer le README du dépôt partagé

**Files:**
- Create: `~/.claude-shared/README.md`

**Step 1: Écrire la documentation**

```markdown
# .claude-shared

Composants partagés du système d'analyse de code CRE.

## Installation dans un nouveau projet

```bash
# Cloner ce repo (ou l'ajouter en submodule)
git clone <url> ~/.claude-shared

# Installer dans un projet
cd /path/to/your/project
~/.claude-shared/install.sh .

# Configurer
nano .claude/config/agentdb.yaml

# Initialiser la base de données
pip install -r .claude/agentdb/requirements.txt
python .claude/scripts/bootstrap.py --full
```

## Structure

```
.claude-shared/
├── agentdb/          # Librairie Python AgentDB
├── agents/           # Prompts des 7 agents d'analyse
├── commands/         # Commandes Claude (/analyze, etc.)
├── mcp/              # Serveur MCP pour Claude Code
├── scripts/          # Bootstrap, maintenance
├── tests/            # Tests unitaires
├── install.sh        # Script d'installation
└── update-shared.sh  # Synchronisation depuis source
```

## Mise à jour

Pour propager les changements du projet source:

```bash
cd ~/.claude-shared
./update-shared.sh /path/to/source/project
git push
```

Dans les projets utilisant ce repo:

```bash
cd /path/to/project/.claude-shared
git pull
```

## Architecture

Chaque projet a:
- **Partagé** (symlinks): agentdb/, agents/, commands/, mcp/, scripts/, tests/
- **Local** (données): data/db.sqlite, config/, reports/, logs/

Les mises à jour du code partagé sont automatiquement appliquées via les symlinks.
```

**Step 2: Commit**

```bash
cd ~/.claude-shared
git add README.md
git commit -m "docs: add README with installation instructions"
```

---

## Task 9: Tester l'installation sur un projet existant

**Files:**
- Test on: `/home/simia/dev/corpo/cre/flow` (restructuration)

**Step 1: Backup de l'existant**

```bash
cd /home/simia/dev/corpo/cre/flow
cp -r .claude .claude.backup
```

**Step 2: Extraire les données projet-spécifiques**

```bash
mkdir -p .claude/data
mv .claude/agentdb/*.sqlite* .claude/data/
mv .claude/agentdb/*.json .claude/data/ 2>/dev/null || true
```

**Step 3: Remplacer par les symlinks**

```bash
# Supprimer les composants qui seront partagés
rm -rf .claude/agentdb/*.py
rm -rf .claude/agentdb/schema.sql
rm -rf .claude/agentdb/query.sh
rm -rf .claude/agentdb/requirements.txt
rm -rf .claude/agents
rm -rf .claude/commands
rm -rf .claude/mcp
rm -rf .claude/scripts
rm -rf .claude/tests

# Créer les symlinks
ln -sfn ~/.claude-shared/agentdb .claude/agentdb
ln -sfn ~/.claude-shared/agents .claude/agents
ln -sfn ~/.claude-shared/commands .claude/commands
ln -sfn ~/.claude-shared/mcp .claude/mcp
ln -sfn ~/.claude-shared/scripts .claude/scripts
ln -sfn ~/.claude-shared/tests .claude/tests
```

**Step 4: Vérifier le fonctionnement**

```bash
# Test query.sh
export AGENTDB_PATH=.claude/data/db.sqlite
bash .claude/agentdb/query.sh list_critical_files

# Test bootstrap (incremental)
python .claude/scripts/bootstrap.py --incremental
```

**Step 5: Commit la nouvelle structure**

Si tout fonctionne:

```bash
rm -rf .claude.backup
git add .claude
git commit -m "refactor: switch to modular .claude structure"
```

---

## Task 10: Créer un script de migration `migrate-to-modular.sh`

**Files:**
- Create: `~/.claude-shared/migrate-to-modular.sh`

**Step 1: Écrire le script de migration**

```bash
#!/bin/bash
# migrate-to-modular.sh - Migre un projet existant vers la structure modulaire
# Usage: ./migrate-to-modular.sh [project-path]

set -e

PROJECT_ROOT="${1:-.}"
CLAUDE_SHARED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$PROJECT_ROOT/.claude"

echo "=== Migration vers structure modulaire ==="
echo "Projet: $PROJECT_ROOT"
echo ""

# Vérifier que .claude existe
if [ ! -d "$CLAUDE_DIR" ]; then
    echo "Erreur: $CLAUDE_DIR n'existe pas"
    echo "Utilisez install.sh pour une nouvelle installation"
    exit 1
fi

# Backup
BACKUP_DIR="$CLAUDE_DIR.backup.$(date +%Y%m%d_%H%M%S)"
echo "Création du backup: $BACKUP_DIR"
cp -r "$CLAUDE_DIR" "$BACKUP_DIR"

# Créer structure data
echo "Création de .claude/data/"
mkdir -p "$CLAUDE_DIR/data"

# Migrer les fichiers de données
echo "Migration des fichiers de données..."
mv "$CLAUDE_DIR/agentdb/"*.sqlite* "$CLAUDE_DIR/data/" 2>/dev/null || true
mv "$CLAUDE_DIR/agentdb/"*.json "$CLAUDE_DIR/data/" 2>/dev/null || true

# Supprimer les anciens composants
echo "Suppression des anciens composants..."
rm -rf "$CLAUDE_DIR/agentdb"
rm -rf "$CLAUDE_DIR/agents"
rm -rf "$CLAUDE_DIR/commands"
rm -rf "$CLAUDE_DIR/mcp"
rm -rf "$CLAUDE_DIR/scripts"
rm -rf "$CLAUDE_DIR/tests"

# Créer les symlinks
echo "Création des symlinks..."
ln -sfn "$CLAUDE_SHARED_DIR/agentdb" "$CLAUDE_DIR/agentdb"
ln -sfn "$CLAUDE_SHARED_DIR/agents" "$CLAUDE_DIR/agents"
ln -sfn "$CLAUDE_SHARED_DIR/commands" "$CLAUDE_DIR/commands"
ln -sfn "$CLAUDE_SHARED_DIR/mcp" "$CLAUDE_DIR/mcp"
ln -sfn "$CLAUDE_SHARED_DIR/scripts" "$CLAUDE_DIR/scripts"
ln -sfn "$CLAUDE_SHARED_DIR/tests" "$CLAUDE_DIR/tests"

# Créer query-local.sh
cat > "$CLAUDE_DIR/query-local.sh" << 'EOF'
#!/bin/bash
export AGENTDB_PATH="${AGENTDB_PATH:-$(dirname "$0")/data/db.sqlite}"
exec "$(dirname "$0")/agentdb/query.sh" "$@"
EOF
chmod +x "$CLAUDE_DIR/query-local.sh"

echo ""
echo "=== Migration terminée ==="
echo ""
echo "Structure:"
ls -la "$CLAUDE_DIR/"
echo ""
echo "Pour tester:"
echo "  export AGENTDB_PATH=$CLAUDE_DIR/data/db.sqlite"
echo "  bash $CLAUDE_DIR/agentdb/query.sh list_critical_files"
echo ""
echo "Backup disponible: $BACKUP_DIR"
echo "Supprimer après validation: rm -rf $BACKUP_DIR"
```

**Step 2: Commit**

```bash
chmod +x ~/.claude-shared/migrate-to-modular.sh
cd ~/.claude-shared
git add migrate-to-modular.sh
git commit -m "feat: add migrate-to-modular.sh for existing projects"
```

---

## Résumé des Fichiers Créés

| Fichier | Rôle |
|---------|------|
| `~/.claude-shared/install.sh` | Installation dans un nouveau projet |
| `~/.claude-shared/update-shared.sh` | Sync depuis le projet source |
| `~/.claude-shared/migrate-to-modular.sh` | Migration d'un projet existant |
| `~/.claude-shared/.gitignore` | Exclusion des données |
| `~/.claude-shared/README.md` | Documentation |

## Workflow Final

```
┌─────────────────────────────────────────────────────────────┐
│  PROJET SOURCE (flow)                                       │
│  - Développement des agents, scripts, etc.                  │
│  - ./update-shared.sh pour publier                          │
└──────────────────────┬──────────────────────────────────────┘
                       │ sync
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  ~/.claude-shared (GIT REPO)                                │
│  - Code partagé uniquement                                  │
│  - git push pour distribuer                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │ symlinks
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Projet A    │ │  Projet B    │ │  Projet C    │
│  .claude/    │ │  .claude/    │ │  .claude/    │
│  ├─ data/    │ │  ├─ data/    │ │  ├─ data/    │
│  │  └─ *.db  │ │  │  └─ *.db  │ │  │  └─ *.db  │
│  ├─ config/  │ │  ├─ config/  │ │  ├─ config/  │
│  └─ agents→  │ │  └─ agents→  │ │  └─ agents→  │
│     (symlink)│ │     (symlink)│ │     (symlink)│
└──────────────┘ └──────────────┘ └──────────────┘
```

## Mise à Jour des Projets

Quand tu modifies `.claude-shared`:

```bash
# 1. Dans le projet source
cd /home/simia/dev/corpo/cre/flow
# ... faire les modifications ...

# 2. Synchroniser vers shared
cd ~/.claude-shared
./update-shared.sh /home/simia/dev/corpo/cre/flow
git push

# 3. Dans chaque projet (automatique via symlinks!)
# Rien à faire si symlinks, sinon:
cd /path/to/project-a/.claude-shared
git pull
```
