# CLAUDE.md

## Projet
Système d'analyse de code avec 5 agents + AgentDB.

## Installation AgentDB
Avant d'utiliser `bootstrap.py --full`, installer les dépendances :

```bash
pip install -r .claude/agentdb/requirements.txt
```

Ou manuellement :
```bash
# Core parsing (tree-sitter moderne)
pip install tree-sitter tree-sitter-python tree-sitter-c tree-sitter-cpp tree-sitter-javascript

# Semantic indexing (embeddings)
pip install numpy sentence-transformers

# Config
pip install pyyaml
```

## Commandes
- `/analyze` : Lancer l'analyse incrémentale
- `python .claude/scripts/bootstrap.py --full` : Initialisation complète de la DB
- `python .claude/scripts/bootstrap.py --incremental` : Mettre à jour la DB

## Règles
- Toujours utiliser AGENTDB_CALLER dans les appels query.sh
- Ne jamais modifier les agents sans tester

## LSP
- Travail sur fichier unique : laisser les diagnostics arriver via Read/Edit
- Audit/scan projet : utiliser `LSP(documentSymbol)` sur les fichiers concernés
- Navigation : utiliser `LSP(goToDefinition)`, `LSP(findReferences)`, `LSP(hover)`
- Toujours vérifier les `<new-diagnostics>` dans les résultats