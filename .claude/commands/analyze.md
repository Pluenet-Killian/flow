---
name: analyze
description: Lance une analyse de code avec les 5 agents (analyzer, security, reviewer, risk, synthesis).
  Le contexte git (commits, fichiers) est pré-calculé par main.py.
---

# Commande /analyze - Analyse de Code

Tu dois orchestrer une analyse du code en utilisant les 5 agents spécialisés et AgentDB.

---

## CONTEXTE GIT (pré-calculé par main.py)

| Paramètre | Valeur |
|-----------|--------|
| **Branche** | $BRANCH_NAME |
| **Branche parente** | $PARENT_BRANCH |
| **Mode détection** | $DETECTION_MODE |
| **From commit** | $FROM_COMMIT_SHORT |
| **To commit** | $TO_COMMIT_SHORT |
| **Fichiers** | $FILES_COUNT fichiers à analyser |

### Fichiers modifiés :
$FILES_LIST

### Stats :
```
$STATS
```

---

## ÉTAPE 0 : Initialisation (logs + AgentDB)

**Avant toute analyse, nettoyer les logs et mettre à jour AgentDB.**

### 0a. Nettoyer les logs de la session précédente

```bash
# Réinitialiser le fichier de log pour cette session d'analyse
LOG_FILE=".claude/logs/agentdb_queries.log"
mkdir -p .claude/logs 2>/dev/null || true
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [system] === NEW ANALYSIS SESSION ===" > "$LOG_FILE"
```

### 0b. Mettre à jour AgentDB (incrémental)

```bash
# Mettre à jour AgentDB de manière incrémentale
python .claude/scripts/bootstrap.py --incremental 2>/dev/null || true
```

**Comportement** :
- Logs : Réinitialisés à chaque analyse
- AgentDB : Si la base n'existe pas, affiche un avertissement mais continue
- En cas d'erreur : continue l'analyse (AgentDB est optionnel)

---

## ÉTAPE 1 : Vérifier les fichiers à analyser

Le contexte git est **déjà calculé** par main.py. Tu reçois directement :
- `$FROM_COMMIT` / `$FROM_COMMIT_SHORT` : Commit de départ
- `$TO_COMMIT` / `$TO_COMMIT_SHORT` : Commit de fin
- `$FILES_LIST` : Liste des fichiers modifiés
- `$FILES_COUNT` : Nombre de fichiers

**Si $FILES_COUNT == 0** :

```
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║  ✅ Aucun fichier de code à analyser                          ║
║                                                               ║
║  From : $FROM_COMMIT_SHORT                                    ║
║  To   : $TO_COMMIT_SHORT                                      ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
```

**TERMINER ICI si aucun fichier à analyser.**

---

## ÉTAPE 2 : Transformer le rapport SonarQube (optionnel)

**Cette étape est optionnelle.** Si aucun rapport SonarQube n'est disponible, continuer normalement.

### Vérifier la présence du rapport SonarQube

```bash
SONAR_INPUT=".claude/sonar/issues.json"
SONAR_AVAILABLE=false

if [ -f "$SONAR_INPUT" ]; then
    SONAR_AVAILABLE=true
    echo "Rapport SonarQube détecté : $SONAR_INPUT"
else
    echo "Pas de rapport SonarQube trouvé, analyse sans SonarQube"
fi
```

### Si le rapport existe, le transformer

```bash
if [ "$SONAR_AVAILABLE" = "true" ]; then
    DATE=$(date +%Y-%m-%d)
    REPORT_DIR=".claude/reports/${DATE}-$TO_COMMIT_SHORT"
    mkdir -p "$REPORT_DIR"

    # Liste des fichiers du diff
    FILES_LIST_CSV=$(echo "$FILES_LIST" | tr '\n' ',' | sed 's/,$//' | sed 's/  - //g')

    # Générer le rapport filtré sur les fichiers du diff
    python .claude/scripts/transform-sonar.py "$SONAR_INPUT" \
        --files "$FILES_LIST_CSV" \
        --commit "$TO_COMMIT_SHORT" \
        --branch "$BRANCH_NAME" \
        --output "$REPORT_DIR/sonar.md"

    if [ $? -eq 0 ]; then
        SONAR_REPORT="$REPORT_DIR/sonar.md"
        SONAR_ISSUES_JSON="$REPORT_DIR/sonar-issues.json"
        echo "Rapport SonarQube généré : $SONAR_REPORT"
    else
        echo "Erreur transformation SonarQube, analyse sans SonarQube"
        SONAR_AVAILABLE=false
    fi
fi
```

---

## ÉTAPE 3 : Afficher le résumé avant analyse

```
╔═══════════════════════════════════════════════════════════════╗
║  ANALYSE DE CODE                                              ║
╠═══════════════════════════════════════════════════════════════╣
║  Branche        : $BRANCH_NAME                                ║
║  Branche parent : $PARENT_BRANCH                              ║
║  Mode           : $DETECTION_MODE                             ║
║  From           : $FROM_COMMIT_SHORT                          ║
║  To             : $TO_COMMIT_SHORT                            ║
║  Fichiers       : $FILES_COUNT fichiers à analyser            ║
║  SonarQube      : {Disponible/Non disponible}                 ║
╠═══════════════════════════════════════════════════════════════╣
║  Fichiers modifiés :                                          ║
$FILES_LIST
╚═══════════════════════════════════════════════════════════════╝
```

---

## ÉTAPE 4 : Récupérer le contexte Jira (optionnel)

Si le MCP Jira est configuré, extraire les informations du ticket associé.

Utilise l'outil MCP `mcp__jira__get_issue_from_text` avec le message du commit.

**Important** : L'absence de contexte Jira ne doit JAMAIS bloquer l'analyse.

---

## ÉTAPE 5 : Préparer le contexte pour les agents

Pour chaque fichier modifié, récupérer :

```bash
# Diff unifié (utiliser les commits fournis)
git diff $FROM_COMMIT..$TO_COMMIT -- "path/to/file.cpp"

# Stats
git diff $FROM_COMMIT..$TO_COMMIT --stat -- "path/to/file.cpp"
```

---

## ÉTAPE 6 : Lancer les agents

### Ordre d'exécution OBLIGATOIRE (4 phases)

```
┌─────────────────────────────────────────────────────────────────┐
│                     PHASE 1 : PARALLÈLE                         │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐                    │
│   │ ANALYZER │   │ SECURITY │   │ REVIEWER │                    │
│   └────┬─────┘   └────┬─────┘   └────┬─────┘                    │
│        └──────────────┼──────────────┘                           │
│                       ▼                                          │
├─────────────────────────────────────────────────────────────────┤
│                     PHASE 2 : RISK puis PARALLÈLE               │
│                 ┌──────────┐                                     │
│                 │   RISK   │  ← Reçoit les 3 rapports           │
│                 └────┬─────┘                                     │
│        ┌─────────────┴─────────────┐                             │
│   ┌────┴─────┐               ┌─────┴────┐                        │
│   │SYNTHESIS │               │  SONAR   │ (si SonarQube dispo)   │
│   └────┬─────┘               └────┬─────┘                        │
│        └──────────┬───────────────┘                              │
│                   ▼                                              │
├─────────────────────────────────────────────────────────────────┤
│                     PHASE 3 : FUSION                            │
│            ┌───────────────────┐                                 │
│            │  META-SYNTHESIS   │ ← Fusionne SYNTHESIS + SONAR   │
│            └────────┬──────────┘                                 │
│                     ▼                                            │
├─────────────────────────────────────────────────────────────────┤
│                     PHASE 4 : WEB EXPORT                        │
│           ┌─────────────────┐                                    │
│           │ WEB SYNTHESIZER │  ← Transforme pour le site web    │
│           └─────────────────┘                                    │
│                     │                                            │
│                     ▼                                            │
│           reports/web-report-{date}-{commit}.json                │
└─────────────────────────────────────────────────────────────────┘
```

### PHASE 1 : Lancer ANALYZER, SECURITY, REVIEWER EN PARALLÈLE

**CRITIQUE** : Tu DOIS lancer ces 3 agents **dans un seul message** avec **3 appels Task tool simultanés**.

| Agent | subagent_type | Query AgentDB obligatoires |
|-------|---------------|---------------------------|
| ANALYZER | `analyzer` | file_context, symbol_callers, file_impact |
| SECURITY | `security` | error_history, patterns (category=security) |
| REVIEWER | `reviewer` | patterns, file_metrics, architecture_decisions |

### PHASE 2 : Lancer RISK puis SYNTHESIS et SONAR (parallèle)

**Attendre** que les 3 agents de Phase 1 soient terminés.

1. **D'abord RISK** : Lancer l'agent RISK avec les résultats des 3 agents Phase 1
2. **Puis en parallèle** :
   - **SYNTHESIS** : Agrège les rapports des 4 agents
   - **SONAR** (si SonarQube disponible) : Enrichit les issues SonarQube

| Agent | subagent_type | Input | Condition |
|-------|---------------|-------|-----------|
| RISK | `risk` | Rapports ANALYZER, SECURITY, REVIEWER | Toujours |
| SYNTHESIS | `synthesis` | Rapports des 4 agents | Toujours |
| SONAR | `sonar` | sonar-issues.json + contexte | Si SonarQube disponible |

### PHASE 3 : Lancer META-SYNTHESIS

**Attendre** que SYNTHESIS et SONAR (si lancé) soient terminés.

| Agent | subagent_type | Input |
|-------|---------------|-------|
| META-SYNTHESIS | `meta-synthesis` | Rapports SYNTHESIS + SONAR (si disponible) |

### PHASE 4 : Lancer WEB SYNTHESIZER

**Attendre** que META-SYNTHESIS soit terminé.

| Agent | subagent_type | Input |
|-------|---------------|-------|
| WEB SYNTHESIZER | `web-synthesizer` | Rapport META-SYNTHESIS |

---

## ÉTAPE 7 : Créer le dossier de rapport

```bash
DATE=`date +%Y-%m-%d`
REPORT_DIR=".claude/reports/${DATE}-$TO_COMMIT_SHORT"
mkdir -p "$REPORT_DIR"
```

---

## ÉTAPE 8 : Sauvegarder les rapports

```
.claude/reports/{date}-{commit}/
├── analyzer.md              # Phase 1 - Agent ANALYZER
├── security.md              # Phase 1 - Agent SECURITY
├── reviewer.md              # Phase 1 - Agent REVIEWER
├── risk.md                  # Phase 2 - Agent RISK
├── REPORT.md                # Phase 2 - Agent SYNTHESIS
├── sonar.md                 # Phase 2 - Script transform-sonar.py (optionnel)
├── sonar-issues.json        # Phase 2 - Script transform-sonar.py (optionnel)
├── sonar-enriched.md        # Phase 2 - Agent SONAR (optionnel)
├── sonar-enriched.json      # Phase 2 - Agent SONAR (optionnel)
├── meta-synthesis.json      # Phase 3 - Agent META-SYNTHESIS
└── meta-synthesis-report.md # Phase 3 - Agent META-SYNTHESIS
```

---

## ÉTAPE 9 : Valider le rapport web

```bash
DATE=$(date +%Y-%m-%d)
WEB_REPORT="reports/web-report-${DATE}-$TO_COMMIT_SHORT.json"

echo "Validation du rapport web..."
python .claude/scripts/validate-web-report.py "$WEB_REPORT"

if [ $? -ne 0 ]; then
    echo "ERREUR: Le rapport web ne respecte pas le format attendu"
    exit 1
fi

echo "Rapport web validé avec succès"
```

---

## ÉTAPE 10 : Afficher le verdict final

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

---

## Verdicts possibles

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

---

## Prompts pour les agents

### Prompt ANALYZER

```
Analyse l'impact des modifications suivantes :

**Type d'analyse** : Diff unifié entre $FROM_COMMIT_SHORT et $TO_COMMIT_SHORT
**Branche** : $BRANCH_NAME

**Fichiers modifiés** :
$FILES_LIST

**Diff résumé** :
$STATS

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

**Type d'analyse** : Diff unifié entre $FROM_COMMIT_SHORT et $TO_COMMIT_SHORT
**Fichiers modifiés** :
$FILES_LIST

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

**Type d'analyse** : Diff unifié entre $FROM_COMMIT_SHORT et $TO_COMMIT_SHORT
**Fichiers modifiés** :
$FILES_LIST

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

**Type d'analyse** : Diff unifié entre $FROM_COMMIT_SHORT et $TO_COMMIT_SHORT
**Fichiers modifiés** :
$FILES_LIST

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

**Type d'analyse** : Diff unifié entre $FROM_COMMIT_SHORT et $TO_COMMIT_SHORT
**Branche** : $BRANCH_NAME
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
5. Produis le rapport final avec TOUS les findings des agents

FORMAT DE SORTIE OBLIGATOIRE : Utilise le format défini dans .claude/agents/synthesis.md
```

### Prompt SONAR

```
Enrichis les issues SonarQube avec le contexte du projet via AgentDB.

**Type d'analyse** : Diff unifié entre $FROM_COMMIT_SHORT et $TO_COMMIT_SHORT
**Branche** : $BRANCH_NAME

**Fichiers du diff** :
$FILES_LIST

**Fichier SonarQube issues** : .claude/reports/{date}-$TO_COMMIT_SHORT/sonar-issues.json

INSTRUCTIONS :
1. Lis le fichier sonar-issues.json
2. Pour CHAQUE issue, appelle AgentDB pour enrichir le contexte
3. Enrichis les sections where/why/how avec le contexte du projet
4. Vérifie que CHAQUE issue a where/why/how NON VIDES
5. Produis sonar-enriched.json pour META-SYNTHESIS

FORMAT DE SORTIE OBLIGATOIRE : Utilise le format défini dans .claude/agents/sonar.md
```

### Prompt META-SYNTHESIS

```
Fusionne et dédoublonne les rapports SYNTHESIS et SONAR.

**Type d'analyse** : Diff unifié entre $FROM_COMMIT_SHORT et $TO_COMMIT_SHORT
**Branche** : $BRANCH_NAME

**Dossier de rapport** : .claude/reports/{date}-$TO_COMMIT_SHORT/

INSTRUCTIONS :
1. Lis le rapport SYNTHESIS et extrait TOUS les findings
2. Si disponible, lis sonar-enriched.json avec les issues SonarQube
3. Fusionne toutes les issues dans une liste unique
4. Détecte les doublons (même fichier + ligne ±5 + même catégorie)
5. Fusionne les doublons en combinant leurs sources
6. Génère where/why/how pour les issues agents qui n'en ont pas
7. VÉRIFIE que CHAQUE issue a where/why/how NON VIDES
8. Produis meta-synthesis.json pour WEB-SYNTHESIZER

FORMAT DE SORTIE OBLIGATOIRE : Utilise le format défini dans .claude/agents/meta-synthesis.md
```

### Prompt WEB SYNTHESIZER

```
Transforme le rapport META-SYNTHESIS en format compatible avec le site web.

**Rapport META-SYNTHESIS** : .claude/reports/{date}-$TO_COMMIT_SHORT/meta-synthesis.json
**Commit** : $TO_COMMIT_SHORT
**Branche** : $BRANCH_NAME

INSTRUCTIONS :
1. Lis le fichier meta-synthesis.json
2. Transforme chaque issue en format attendu par le site web
3. Crée le tableau `issues[]` avec les bons champs
4. Crée l'objet `issueDetails{}` avec where/why/how pour CHAQUE issue
5. VÉRIFIE que `issues.length === Object.keys(issueDetails).length`
6. Sauvegarde dans reports/web-report-{date}-$TO_COMMIT_SHORT.json

FORMAT DE SORTIE OBLIGATOIRE : Utilise le format défini dans .claude/agents/web-synthesizer.md
```

---

## Gestion des erreurs

- Si un agent échoue, continuer avec les autres
- Signaler l'erreur dans le rapport final
- Ne jamais bloquer à cause d'AgentDB manquant

---

## Exécution

Maintenant, exécute l'analyse en suivant les étapes ci-dessus.

0. Mets à jour AgentDB (`python .claude/scripts/bootstrap.py --incremental`)
1. Vérifie s'il y a des fichiers à analyser ($FILES_COUNT)
2. Si aucun fichier : affiche "Rien à analyser" et TERMINE
3. Transforme le rapport SonarQube si disponible
4. Lance les agents :
   - **PHASE 1** : analyzer/security/reviewer EN PARALLÈLE
   - **PHASE 2** : risk, puis synthesis/sonar EN PARALLÈLE
   - **PHASE 3** : meta-synthesis
   - **PHASE 4** : web-synthesizer
5. **Valide le rapport web** (`python .claude/scripts/validate-web-report.py`)
6. Affiche le verdict final
