# AgentDB v6 "Lean" Architecture

## Philosophie

AgentDB v6 adopte une architecture **complémentaire à LSP**, en se concentrant uniquement sur ce que le Language Server Protocol natif de Claude Code ne fournit pas.

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLAUDE CODE                                 │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    LSP NATIF                             │   │
│  │  Navigation • Références • Call Hierarchy • Symbols      │   │
│  │                                                          │   │
│  │  goToDefinition    findReferences    documentSymbol      │   │
│  │  goToImplementation incomingCalls    workspaceSymbol     │   │
│  │  hover             outgoingCalls     prepareCallHierarchy│   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               AGENTDB v6 "LEAN"                          │   │
│  │  Contexte Historique • Sémantique • Learning • Métriques │   │
│  │                                                          │   │
│  │  Ce que LSP NE FAIT PAS:                                 │   │
│  │  - Mémoire des bugs passés                               │   │
│  │  - Recherche en langage naturel                          │   │
│  │  - Apprentissage depuis Git                              │   │
│  │  - Score de risque                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Les 12 Outils v6

### Catégorie 1: Contexte & Historique (4 outils)

| Outil | Description | LSP Équivalent |
|-------|-------------|----------------|
| `get_file_context` | Contexte 360° d'un fichier | Aucun |
| `get_error_history` | Historique des bugs | Aucun |
| `get_patterns` | Conventions de code | Aucun |
| `get_architecture_decisions` | ADRs | Aucun |

### Catégorie 2: Métriques & Risque (3 outils)

| Outil | Description | LSP Équivalent |
|-------|-------------|----------------|
| `get_file_metrics` | Métriques + score de risque | Aucun |
| `get_module_summary` | Vue d'ensemble d'un module | Aucun |
| `get_risk_assessment` | Évaluation de risque PR | Aucun |

### Catégorie 3: Recherche Sémantique (2 outils)

| Outil | Description | LSP Équivalent |
|-------|-------------|----------------|
| `semantic_search` | Recherche en langage naturel | workspaceSymbol (nom exact) |
| `find_similar_code` | Trouver du code similaire | Aucun |

### Catégorie 4: Pattern Learning (3 outils)

| Outil | Description | LSP Équivalent |
|-------|-------------|----------------|
| `learn_from_history` | Apprendre depuis Git | Aucun |
| `detect_code_smells` | Détecter les anti-patterns | Aucun |
| `get_suggestions` | Suggestions d'amélioration | Aucun |

## Outils Supprimés (Redondants avec LSP)

| Ancien Outil | Raison | Alternative LSP |
|--------------|--------|-----------------|
| `get_symbol_callers` | Redondant | `LSP incomingCalls` |
| `get_symbol_callees` | Redondant | `LSP outgoingCalls` |
| `get_file_impact` | Partiellement redondant | `LSP findReferences` |
| `search_symbols` | Redondant | `LSP workspaceSymbol` |
| `smart_references` | Redondant | `LSP findReferences` |
| `smart_callers` | Redondant | `LSP incomingCalls` |
| `impact_analysis_v2` | Redondant | `LSP + get_risk_assessment` |
| `smart_search` | Redondant | `LSP workspaceSymbol` |
| `parse_file` | Redondant | `LSP documentSymbol` |
| `get_supported_languages` | Debug only | - |
| `get_embedding_stats` | Debug only | - |
| `get_learning_stats` | Debug only | - |
| `record_learning_feedback` | Rarement utilisé | - |

## Quand Utiliser Quoi ?

### Navigation et Références → LSP

```
"Où est définie cette fonction ?" → LSP goToDefinition
"Qui appelle cette fonction ?" → LSP incomingCalls
"Quelles fonctions appelle-t-elle ?" → LSP outgoingCalls
"Tous les usages de ce symbole ?" → LSP findReferences
"Liste des fonctions du fichier ?" → LSP documentSymbol
```

### Contexte et Historique → AgentDB

```
"Ce fichier a-t-il eu des bugs ?" → get_error_history
"Quelles conventions suivre ?" → get_patterns
"Pourquoi ce design ?" → get_architecture_decisions
"Ce fichier est-il risqué ?" → get_file_metrics
```

### Recherche Intelligente → AgentDB

```
"Code qui gère l'authentification" → semantic_search
"Fonctions similaires à celle-ci" → find_similar_code
```

### Qualité et Amélioration → AgentDB

```
"Problèmes dans ce fichier ?" → detect_code_smells
"Comment améliorer ce code ?" → get_suggestions
"Erreurs récurrentes ?" → learn_from_history
```

## Flux de Travail Recommandé

### Avant de modifier un fichier

1. **LSP** `documentSymbol` → Structure du fichier
2. **AgentDB** `get_file_context` → Historique, patterns, métriques
3. **AgentDB** `get_suggestions` → Problèmes existants

### Pendant la modification

1. **LSP** `goToDefinition` → Navigation
2. **LSP** `findReferences` → Impact immédiat
3. **AgentDB** `semantic_search` → Trouver du code similaire

### Avant de merger (PR Review)

1. **AgentDB** `get_risk_assessment` → Score de risque global
2. **AgentDB** `detect_code_smells` → Anti-patterns introduits
3. **LSP** `findReferences` → Vérifier les impacts

## Comparaison v5 vs v6

| Métrique | v5 | v6 Lean |
|----------|-----|---------|
| Outils MCP | 25 | 12 |
| Redondance avec LSP | ~50% | 0% |
| Focus | Tout faire | Compléter LSP |
| Maintenance | Complexe | Simple |

## Migration depuis v5

Si vous utilisiez des outils supprimés, voici les alternatives :

```python
# Avant (v5)
get_symbol_callers("my_function")

# Après (v6)
# Utilisez LSP incomingCalls directement dans Claude Code
# LSP incomingCalls sur my_function
```

```python
# Avant (v5)
search_symbols("init*")

# Après (v6)
# Utilisez LSP workspaceSymbol
# LSP workspaceSymbol "init*"
```

## Dépendances

### Requises
- Python 3.10+
- SQLite 3

### Optionnelles (pour features avancées)
```bash
# Recherche sémantique
pip install sentence-transformers numpy

# Multi-langage (bootstrap uniquement)
pip install "tree-sitter<0.21" tree-sitter-languages
```

## Architecture Interne

```
.claude/
├── agentdb/
│   ├── db.sqlite              # Base de données
│   ├── schema.sql             # Schéma (8 piliers)
│   ├── semantic.py            # Embeddings
│   ├── pattern_learner.py     # Apprentissage
│   └── tree_sitter_parser.py  # Multi-lang (bootstrap)
├── mcp/agentdb/
│   ├── server.py              # Serveur MCP v6 (12 outils)
│   ├── tools.py               # Handlers v1
│   └── tools_v2.py            # Handler risk_assessment
└── scripts/
    └── bootstrap.py           # Indexation (11 étapes)
```

## Versioning

- **v1-v5**: Croissance des fonctionnalités
- **v6 "Lean"**: Optimisation et focus sur la valeur ajoutée

La version 6 marque un changement de philosophie: au lieu d'essayer de tout faire, AgentDB se concentre sur ce qu'il fait mieux que LSP.
