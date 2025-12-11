---
name: analyze
description: |
  Lance une analyse complète du code avec les 5 agents (analyzer, security, reviewer, risk, synthesis).
  Produit un rapport avec verdict dans .claude/reports/.
  Usage:
  - /analyze              : Analyse le dernier commit (HEAD)
  - /analyze abc123       : Analyse un commit spécifique
  - /analyze --files src/file.cpp : Analyse des fichiers spécifiques
  - /analyze --branch feature/x   : Analyse une branche vs main
---

# Commande /analyze

Tu dois orchestrer une analyse complète du code en utilisant les 5 agents spécialisés et AgentDB.

## ARGUMENT REÇU

$ARGUMENTS

## ÉTAPE 1 : Parser les arguments et déterminer quoi analyser

### Règles de parsing

1. **Pas d'argument** (`$ARGUMENTS` est vide) :
   - Analyser les fichiers modifiés dans le dernier commit (HEAD vs HEAD~1)
   - Commande : `git diff HEAD~1 --name-only`

2. **Hash de commit** (ex: `abc123`, `fe11a62`) :
   - Analyser les fichiers modifiés dans ce commit spécifique
   - Commande : `git diff <hash>~1 <hash> --name-only`

3. **Option `--files`** (ex: `--files src/server/UDPServer.cpp src/core/Config.hpp`) :
   - Analyser uniquement les fichiers spécifiés
   - Vérifier que chaque fichier existe

4. **Option `--branch`** (ex: `--branch feature/new-feature`) :
   - Comparer la branche spécifiée avec main/develop
   - Commande : `git diff main...<branch> --name-only`

### Actions à effectuer

```bash
# Déterminer la méthode d'analyse
if [ -z "$ARGUMENTS" ]; then
    # Cas 1: Analyser HEAD
    git log -1 --format="%H %s" HEAD
    git diff HEAD~1 --name-only --diff-filter=ACMR
elif [[ "$ARGUMENTS" =~ ^--files ]]; then
    # Cas 3: Fichiers spécifiques
    echo "Fichiers spécifiés: $ARGUMENTS"
elif [[ "$ARGUMENTS" =~ ^--branch ]]; then
    # Cas 4: Comparer une branche
    BRANCH=$(echo "$ARGUMENTS" | sed 's/--branch //')
    git diff main...$BRANCH --name-only
else
    # Cas 2: Hash de commit spécifique
    COMMIT="$ARGUMENTS"
    git log -1 --format="%H %s" "$COMMIT"
    git diff ${COMMIT}~1 ${COMMIT} --name-only --diff-filter=ACMR
fi
```

### Filtrer les fichiers

Garder uniquement les fichiers de code :
- Extensions : `.c`, `.cpp`, `.h`, `.hpp`, `.py`, `.js`, `.ts`, `.go`, `.rs`, `.java`
- Ignorer : `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.lock`, images, etc.

## ÉTAPE 1.5 : Récupérer le contexte Jira (optionnel)

Si le MCP Jira est configuré, extraire les informations du ticket associé au commit.

### Extraction automatique depuis le commit message

Utilise l'outil MCP `mcp__jira__get_issue_from_text` avec le message du commit :

```
# Exemple de commit message : "[PROJ-123] Fix login bug"
# L'outil extrait automatiquement PROJ-123 et récupère les infos du ticket
```

### Informations à récupérer

Si un ticket est trouvé, extraire :
- **summary** : Titre du ticket
- **description** : Description complète
- **acceptance_criteria** : Critères d'acceptation (si disponibles)
- **type** : Bug, Story, Task, etc.
- **priority** : Priorité du ticket
- **status** : Statut actuel

### Gestion des erreurs Jira

| Situation | Action |
|-----------|--------|
| MCP Jira non configuré | Continuer sans contexte Jira |
| Pas de ticket dans le commit | Continuer sans contexte Jira |
| Ticket non trouvé (404) | Mentionner dans le rapport, continuer |
| Erreur API Jira | Loguer l'erreur, continuer sans |

**Important** : L'absence de contexte Jira ne doit JAMAIS bloquer l'analyse.

### Intégration dans les prompts

Si un ticket Jira est trouvé, ajouter cette section aux prompts des agents :

```markdown
**Contexte Jira** :
- Ticket : {ticket_key}
- Titre : {summary}
- Type : {type}
- Description : {description}
- Acceptance Criteria : {acceptance_criteria}
```

Cette information aide les agents à :
- **ANALYZER** : Vérifier que l'impact correspond au scope du ticket
- **SECURITY** : Adapter le niveau de scrutiny selon le type (Bug vs Feature)
- **REVIEWER** : Vérifier que le code répond aux acceptance criteria
- **RISK** : Ajuster le risque selon la criticité du ticket

## ÉTAPE 2 : Préparer le contexte pour les agents

Pour chaque fichier modifié, récupérer les informations de base :

```bash
# Pour chaque fichier, obtenir le diff
git diff HEAD~1 -- "path/to/file.cpp"

# Compter les lignes modifiées
git diff HEAD~1 --stat -- "path/to/file.cpp"
```

## ÉTAPE 3 : Lancer les agents

### Ordre d'exécution OBLIGATOIRE

```
┌─────────────────────────────────────────────────────────────────┐
│                     PHASE 1 : PARALLÈLE                         │
│                                                                  │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐                    │
│   │ ANALYZER │   │ SECURITY │   │ REVIEWER │                    │
│   └────┬─────┘   └────┬─────┘   └────┬─────┘                    │
│        │              │              │                           │
│        └──────────────┼──────────────┘                           │
│                       ▼                                          │
├─────────────────────────────────────────────────────────────────┤
│                     PHASE 2 : SÉQUENTIEL                        │
│                       ▼                                          │
│                 ┌──────────┐                                     │
│                 │   RISK   │  ← Reçoit les 3 rapports           │
│                 └────┬─────┘                                     │
│                      ▼                                          │
│                ┌───────────┐                                     │
│                │ SYNTHESIS │  ← Reçoit les 4 rapports           │
│                └───────────┘                                     │
└─────────────────────────────────────────────────────────────────┘
```

### PHASE 1 : Lancer ANALYZER, SECURITY, REVIEWER EN PARALLÈLE

**CRITIQUE** : Tu DOIS lancer ces 3 agents **dans un seul message** avec **3 appels Task tool simultanés**.

Envoie **UN SEUL message** contenant **3 blocs Task tool** :

1. Task #1 : subagent_type="analyzer", prompt={prompt analyzer}
2. Task #2 : subagent_type="security", prompt={prompt security}
3. Task #3 : subagent_type="reviewer", prompt={prompt reviewer}

**NE PAS** attendre le résultat d'un agent avant de lancer les autres.
**NE PAS** envoyer 3 messages séparés.

Chaque agent DOIT utiliser AgentDB. Vérifie dans chaque rapport la présence de la section "AgentDB Data Used".

#### Agents Phase 1 (parallèles)

| Agent | subagent_type | Query AgentDB obligatoires |
|-------|---------------|---------------------------|
| ANALYZER | `analyzer` | file_context, symbol_callers, file_impact |
| SECURITY | `security` | error_history, patterns (category=security) |
| REVIEWER | `reviewer` | patterns, file_metrics, architecture_decisions |

### PHASE 2 : Lancer RISK puis SYNTHESIS (séquentiel)

**Attendre** que les 3 agents de Phase 1 soient terminés, puis :

#### Agent 4 : RISK

```
Utilise le Task tool avec :
- subagent_type: "risk"
- prompt: Contient les résultats des 3 agents précédents

L'agent DOIT appeler :
- query.sh file_context (criticité)
- query.sh file_metrics (complexité)
- query.sh error_history (historique bugs)
```

#### Agent 5 : SYNTHESIS

```
Utilise le Task tool avec :
- subagent_type: "synthesis"
- prompt: Contient les résultats des 4 agents précédents

Produit le rapport final avec le verdict.
```

## ÉTAPE 4 : Créer le dossier de rapport

```bash
# Format: YYYY-MM-DD-<commit_short>
DATE=$(date +%Y-%m-%d)
COMMIT_SHORT=$(git rev-parse --short HEAD)
REPORT_DIR=".claude/reports/${DATE}-${COMMIT_SHORT}"

mkdir -p "$REPORT_DIR"
```

## ÉTAPE 5 : Sauvegarder les rapports

Après chaque agent, sauvegarder son rapport :

```
.claude/reports/{date}-{commit}/
├── analyzer.md      # Rapport de l'agent ANALYZER
├── security.md      # Rapport de l'agent SECURITY
├── reviewer.md      # Rapport de l'agent REVIEWER
├── risk.md          # Rapport de l'agent RISK
└── REPORT.md        # Rapport final de SYNTHESIS
```

## ÉTAPE 6 : Produire le rapport final (REPORT.md)

**Exemple de référence** : Voir `.claude/reports/examples/GOLDEN_REPORT.md` pour un rapport complet.

Le rapport REPORT.md doit contenir :

```markdown
# Rapport d'Analyse

**Date** : {date}
**Commit** : {commit_hash}
**Branche** : {branch_name}
**Fichiers analysés** : {count}

---

## Verdict : {emoji} {VERDICT}

Score global : {score}/100

---

## Données AgentDB Utilisées

| Agent | file_context | symbol_callers | error_history | patterns | file_metrics |
|-------|--------------|----------------|---------------|----------|--------------|
| Analyzer | {status} | {status} | - | - | - |
| Security | {status} | - | {status} | {status} | - |
| Reviewer | {status} | - | - | {status} | {status} |
| Risk | {status} | {status} | {status} | - | {status} |

Légende : ✅ = utilisé avec données, ⚠️ = utilisé mais vide, ❌ = non utilisé, - = non applicable

---

## Résumé par Agent

| Agent | Score | Issues | Status |
|-------|-------|--------|--------|
| Analyzer | {score} | {issues} | {emoji} |
| Security | {score} | {issues} | {emoji} |
| Reviewer | {score} | {issues} | {emoji} |
| Risk | {score} | {issues} | {emoji} |

---

## Issues Critiques

{Liste des issues HIGH et CRITICAL de tous les agents}

---

## Actions Requises

{Checklist des actions à faire avant merge}

---

## Détails

Voir les rapports individuels dans ce dossier.
```

## ÉTAPE 7 : Afficher le verdict dans le chat

À la fin de l'analyse, affiche clairement :

```
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     VERDICT: {emoji} {VERDICT}                                ║
║                                                               ║
║     Score global: {score}/100                                 ║
║                                                               ║
║     {résumé en 2-3 lignes}                                    ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

Rapport complet : .claude/reports/{date}-{commit}/REPORT.md
```

## Verdicts possibles

**Référence** : Seuils configurables dans `.claude/config/agentdb.yaml` section `analysis.verdicts`

| Score | Verdict | Emoji | Signification |
|-------|---------|-------|---------------|
| ≥80 | APPROVE | 🟢 | Peut être mergé |
| ≥60 | REVIEW | 🟡 | Review humaine recommandée |
| ≥40 | CAREFUL | 🟠 | Review approfondie requise |
| <40 | REJECT | 🔴 | Ne pas merger en l'état |

### Règles de décision

```
SI (Security.max_severity == "CRITICAL") OU (Security.regressions > 0) :
    → REJECT (🔴)

SI (Security.max_severity == "HIGH") OU (Risk.score < 60) OU (issues bloquantes) :
    → CAREFUL (🟠)

SI (Reviewer.errors > 0) OU (Risk.score < 80) :
    → REVIEW (🟡)

SINON :
    → APPROVE (🟢)
```

## Gestion des erreurs

- Si un agent échoue, continuer avec les autres
- Signaler l'erreur dans le rapport final
- Si ANALYZER échoue, les autres agents peuvent quand même fonctionner avec les fichiers modifiés
- Si SYNTHESIS échoue, produire un rapport minimal avec les résultats disponibles

## Prompts pour les agents

### Prompt ANALYZER

```
Analyse l'impact des modifications suivantes :

**Commit** : {commit_hash}
**Message** : {commit_message}

**Fichiers modifiés** :
{liste des fichiers avec leurs stats}

**Diff résumé** :
{diff --stat}

INSTRUCTIONS :
1. Pour CHAQUE fichier, appelle `AGENTDB_CALLER="analyzer" bash .claude/agentdb/query.sh file_context "path"`
2. Identifie les fonctions modifiées dans chaque fichier
3. Pour CHAQUE fonction modifiée, appelle `AGENTDB_CALLER="analyzer" bash .claude/agentdb/query.sh symbol_callers "funcName"`
4. Calcule l'impact : LOCAL / MODULE / GLOBAL
5. Produis le rapport avec la section "AgentDB Data Used"

FORMAT DE SORTIE OBLIGATOIRE : Utilise le format défini dans .claude/agents/analyzer.md
```

### Prompt SECURITY

```
Audite la sécurité des modifications suivantes :

**Commit** : {commit_hash}
**Fichiers modifiés** :
{liste des fichiers}

INSTRUCTIONS :
1. Pour CHAQUE fichier, appelle `AGENTDB_CALLER="security" bash .claude/agentdb/query.sh error_history "path"`
2. Vérifie s'il y a des patterns de bugs passés qui réapparaissent (RÉGRESSION)
3. Appelle `AGENTDB_CALLER="security" bash .claude/agentdb/query.sh patterns "" "security"` pour les patterns de sécurité
4. Scanne le code pour les vulnérabilités connues (CWE)
5. Produis le rapport avec la section "AgentDB Data Used"

FORMAT DE SORTIE OBLIGATOIRE : Utilise le format défini dans .claude/agents/security.md
```

### Prompt REVIEWER

```
Effectue une code review des modifications suivantes :

**Commit** : {commit_hash}
**Fichiers modifiés** :
{liste des fichiers}

INSTRUCTIONS :
1. Pour CHAQUE fichier, appelle `AGENTDB_CALLER="reviewer" bash .claude/agentdb/query.sh patterns "path"`
2. Pour CHAQUE fichier, appelle `AGENTDB_CALLER="reviewer" bash .claude/agentdb/query.sh file_metrics "path"`
3. Appelle `AGENTDB_CALLER="reviewer" bash .claude/agentdb/query.sh architecture_decisions` pour les ADRs
4. Vérifie les conventions, la qualité, et l'architecture
5. Produis le rapport avec la section "AgentDB Data Used"

FORMAT DE SORTIE OBLIGATOIRE : Utilise le format défini dans .claude/agents/reviewer.md
```

### Prompt RISK

```
Évalue le risque des modifications suivantes :

**Commit** : {commit_hash}
**Fichiers modifiés** :
{liste des fichiers}

**Résultats des agents précédents** :

ANALYZER :
{résumé du rapport analyzer}

SECURITY :
{résumé du rapport security}

REVIEWER :
{résumé du rapport reviewer}

INSTRUCTIONS :
1. Pour CHAQUE fichier, appelle `AGENTDB_CALLER="risk" bash .claude/agentdb/query.sh file_context "path"` (criticité)
2. Pour CHAQUE fichier, appelle `AGENTDB_CALLER="risk" bash .claude/agentdb/query.sh file_metrics "path"` (complexité)
3. Pour CHAQUE fichier, appelle `AGENTDB_CALLER="risk" bash .claude/agentdb/query.sh error_history "path" 90` (bugs récents)
4. Calcule le score de risque selon la formule
5. Produis le rapport avec la section "AgentDB Data Used"

FORMAT DE SORTIE OBLIGATOIRE : Utilise le format défini dans .claude/agents/risk.md
```

### Prompt SYNTHESIS

```
Synthétise les rapports d'analyse suivants :

**Commit** : {commit_hash}
**Branche** : {branch} → {target_branch}
**Date** : {date}

**RAPPORT ANALYZER** :
{rapport complet analyzer}

**RAPPORT SECURITY** :
{rapport complet security}

**RAPPORT REVIEWER** :
{rapport complet reviewer}

**RAPPORT RISK** :
{rapport complet risk}

INSTRUCTIONS :
1. Parse les scores et findings de chaque agent
2. Calcule le score global (Security×0.35 + Risk×0.25 + Reviewer×0.25 + Analyzer×0.15)
3. Détecte les contradictions entre agents
4. Détermine le verdict : APPROVE / REVIEW / CAREFUL / REJECT
5. Produis le rapport final avec :
   - Executive summary
   - Tableau des données AgentDB utilisées
   - Issues consolidées et priorisées
   - Checklist d'actions

FORMAT DE SORTIE OBLIGATOIRE : Utilise le format défini dans .claude/agents/synthesis.md
```

## Exécution

Maintenant, exécute l'analyse complète en suivant les étapes ci-dessus.
Commence par parser les arguments et récupérer les fichiers modifiés.
