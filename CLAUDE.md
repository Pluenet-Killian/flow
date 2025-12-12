# CLAUDE.md

## Projet
Système d'analyse de code avec 5 agents + AgentDB.

## Commandes
- `/analyze` : Lancer l'analyse incrémentale
- `python .claude/scripts/bootstrap.py --incremental` : Mettre à jour la DB

## Règles
- Toujours utiliser AGENTDB_CALLER dans les appels query.sh
- Ne jamais modifier les agents sans tester