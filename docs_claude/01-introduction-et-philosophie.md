# Introduction et Philosophie

> **AgentDB** - Le cerveau contextuel pour les agents IA de code review

---

## Vue d'ensemble

AgentDB est un **systeme d'indexation de code** sophistique concu pour fournir une memoire contextuelle persistante aux agents IA (Claude). Il transforme l'analyse de code basique en une analyse intelligente et contextuelle en maintenant un graphe de connaissances complet de la structure du code, des evenements historiques, des patterns et des metriques.

```
                    +------------------+
                    |   Agent IA       |
                    |   (Claude)       |
                    +--------+---------+
                             |
                             | MCP Protocol
                             v
                    +------------------+
                    |   AgentDB        |
                    |   10 Outils MCP  |
                    +--------+---------+
                             |
                             v
    +------------------------------------------------+
    |              Base SQLite                       |
    |  +----------+ +----------+ +----------+        |
    |  | Graphe   | | Memoire  | | Base de  |        |
    |  | Deps     | | Hist.    | | Connais. |        |
    |  +----------+ +----------+ +----------+        |
    +------------------------------------------------+
```

---

## Le Probleme Resolu

### Sans AgentDB

Lorsqu'un agent IA analyse du code sans contexte :

| Limitation | Consequence |
|------------|-------------|
| Pas de memoire des bugs passes | Les memes erreurs se repetent |
| Pas de graphe de dependances | Impact des modifications inconnu |
| Pas de patterns documentes | Inconsistance dans le code |
| Pas de decisions architecturales | Violations des standards |

### Avec AgentDB

L'agent dispose d'un **cerveau partage** qui lui permet de :

- **Connaitre l'historique** : "Cette fonction a deja cause un buffer overflow en 2024"
- **Mesurer l'impact** : "Modifier ce fichier affecte 47 autres fichiers"
- **Appliquer les patterns** : "Ce module utilise le pattern error_handling strict"
- **Respecter l'architecture** : "L'ADR-007 interdit les appels directs au hardware"

---

## Les Quatre Piliers Fondamentaux

AgentDB repose sur **quatre piliers** qui repondent chacun a une question fondamentale :

### Pilier 1 : Le Graphe de Dependances

> **Question** : "Si je modifie X, qu'est-ce qui peut casser ?"

```
                    lcd_write()
                        |
          +-------------+-------------+
          |             |             |
     lcd_init()    gpio_set()    delay_ms()
          |             |
    spi_transfer()  port_config()
```

**Tables concernees** :
- `files` - Metadonnees des fichiers avec metriques
- `symbols` - Fonctions, classes, types, macros
- `relations` - Relations symbole-a-symbole
- `file_relations` - Relations fichier-a-fichier

**Capacites** :
- Traversee recursive du graphe (jusqu'a 10 niveaux)
- Analyse d'impact (dependances directes + transitives)
- Detection des chemins critiques

---

### Pilier 2 : La Memoire Historique

> **Question** : "Qu'est-ce qui s'est passe avant ?"

| Type d'erreur | Exemple | Severite |
|---------------|---------|----------|
| `buffer_overflow` | Depassement dans lcd_write | Critical |
| `null_pointer` | ptr non verifie dans init | High |
| `race_condition` | Acces concurrent au SPI | High |
| `memory_leak` | malloc sans free | Medium |

**Tables concernees** :
- `error_history` - Bugs historiques avec resolutions
- `pipeline_runs` - Historique des executions CI/CD
- `snapshot_symbols` - Snapshots pour comparaison

**Capacites** :
- Suivi des bugs avec severite et CWE IDs
- Documentation des causes racines et resolutions
- Detection des regressions

---

### Pilier 3 : La Base de Connaissances

> **Question** : "Comment cela devrait-il etre fait ?"

**Exemple de Pattern** :

```c
// MAUVAIS - Pattern error_handling
int init() {
    setup();  // Retour ignore
    return 0;
}

// BON - Pattern error_handling
int init() {
    int ret = setup();
    if (ret != 0) {
        log_error("Setup failed: %d", ret);
        return ret;
    }
    return 0;
}
```

**Tables concernees** :
- `patterns` - Patterns de code a suivre
- `architecture_decisions` - ADRs (Architecture Decision Records)
- `critical_paths` - Chemins critiques marques

**Categories de patterns supportees** :
- `error_handling` - Gestion des erreurs
- `memory_safety` - Securite memoire
- `naming_convention` - Conventions de nommage
- `security` - Pratiques de securite
- `performance` - Optimisations

---

### Pilier 4 : Les Metriques

> **Question** : "Est-ce complexe ? Est-ce volumineux ?"

| Metrique | Seuil Ideal | Warning | Critique |
|----------|-------------|---------|----------|
| Complexite cyclomatique | < 5 | > 10 | > 20 |
| Lignes par fonction | < 30 | > 50 | > 100 |
| Lignes par fichier | < 300 | > 500 | > 1000 |
| Profondeur d'imbrication | < 3 | > 5 | > 7 |

**Metriques collectees** :
- **Code** : Lignes, complexite, imbrication
- **Documentation** : Score de couverture (0-100)
- **Activite Git** : Commits sur 30/90/365 jours
- **Qualite** : Dette technique, couverture de tests

---

## Architecture de Haut Niveau

```
.claude/
|-- agentdb/                 # Coeur de la bibliotheque
|   |-- schema.sql          # Schema SQLite (11 tables)
|   |-- db.sqlite           # Base principale
|   |-- shared.sqlite       # Base partagee multi-branche
|   |-- models.py           # Modeles de donnees
|   |-- db.py               # Gestion de connexion
|   |-- crud.py             # Operations CRUD (2300+ lignes)
|   |-- queries.py          # Requetes graphe recursives
|   |-- config.py           # Configuration
|   |-- indexer.py          # Parseur de code (1700+ lignes)
|   +-- query.sh            # Interface shell pour agents
|
|-- agents/                  # 8 agents specialises
|   |-- analyzer.md         # Phase 1 - Analyse d'impact
|   |-- security.md         # Phase 1 - Vulnerabilites
|   |-- reviewer.md         # Phase 1 - Code review
|   |-- risk.md             # Phase 1 - Scoring risque
|   |-- synthesis.md        # Phase 2 - Fusion 4 agents
|   |-- sonar.md            # Phase 2 - Enrichit SonarQube
|   |-- meta-synthesis.md   # Phase 3 - Consolidation
|   +-- web-synthesizer.md  # Phase 4 - JSON pour site
|
|-- commands/                # Commandes CLI
|   +-- analyze.md          # /analyze - Orchestration complete
|
|-- mcp/                     # Serveurs MCP
|   |-- agentdb/            # AgentDB MCP (10 outils)
|   +-- jira/               # Jira MCP (optionnel)
|
|-- scripts/                 # Automatisation
|   |-- bootstrap.py        # Initialisation (9 etapes)
|   |-- update.py           # Mise a jour incrementale
|   |-- maintenance.py      # VACUUM, ANALYZE, cleanup
|   +-- transform-sonar.py  # Transformation issues Sonar
|
|-- reports/                 # Rapports generes
|   +-- {date}-{commit}/    # Un dossier par analyse
|
|-- config/                  # Configuration YAML
|-- tests/                   # Suite de tests
|-- logs/                    # Journaux et metriques
|
|-- agentdb_manager.py       # Gestionnaire multi-branche
+-- worktree.py              # Gestionnaire git worktrees
```

---

## Principes de Conception

### 1. Zero Configuration

AgentDB detecte automatiquement :
- Le langage principal du projet
- Les fichiers a indexer
- Les chemins critiques
- Les patterns par defaut

### 2. Performance First

- **SQLite WAL** pour les acces concurrents
- **Requetes CTE recursives** pour le graphe
- **Cache en memoire** pour les lookups frequents
- **Mise a jour incrementale** (cible < 5 secondes)

### 3. Extensibilite

- Configuration YAML complete
- Patterns personnalisables
- Support multi-langages (C, C++, Python, JS, TS, Go, Rust)

### 4. Integration MCP Native

Le protocole MCP (Model Context Protocol) permet une integration transparente avec Claude et d'autres agents IA.

---

## Cas d'Usage Principaux

| Cas d'usage | Outil MCP | Description |
|-------------|-----------|-------------|
| Code Review | `get_file_context` | Contexte complet pour l'analyse |
| Analyse d'Impact | `get_file_impact` | Fichiers affectes par un changement |
| Detection de Regressions | `get_error_history` | Bugs passes similaires |
| Navigation | `search_symbols` | Recherche de symboles |
| Sante Module | `get_module_summary` | Vue agregee d'un module |

---

## Prochaine Etape

Continuez vers [02-architecture-globale.md](./02-architecture-globale.md) pour une vue detaillee de l'architecture avec diagrammes Mermaid.
