# Architecture Hybride LSP + AgentDB v2.0

## Vue d'ensemble

L'architecture hybride combine la puissance du **LSP natif de Claude Code** avec l'**enrichissement contextuel d'AgentDB** pour offrir une analyse de code plus complète et plus rapide.

```
┌─────────────────────────────────────────────────────────────┐
│                    CLAUDE CODE LSP                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │goToDefinition│  │findReferences│  │ incomingCalls      │  │
│  │outgoingCalls │  │    hover    │  │ workspaceSymbol    │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────┬──────────┘  │
└─────────┼────────────────┼───────────────────┼──────────────┘
          │                │                   │
          ▼                ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│              HYBRID LAYER (hybrid_lsp.py)                    │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐                     │
│  │  LSP Results   │──│ AgentDB Enrich │                     │
│  │ (fast, precise)│  │ (context, hist)│                     │
│  └────────────────┘  └────────────────┘                     │
│                                                              │
│  Enrichissements:                                            │
│  - error_history (mémoire des bugs)                         │
│  - criticality_score (fichiers critiques)                   │
│  - git_activity (commits récents)                           │
│  - patterns (règles métier)                                 │
│  - risk_score (évaluation du risque)                        │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                  AGENTDB (base SQLite)                       │
│                                                              │
│  Tables:                                                     │
│  - files, symbols, relations (graphe de code)               │
│  - error_history (mémoire des bugs)                         │
│  - patterns, architecture_decisions (connaissances)         │
│  - analysis_checkpoints (incrémental)                       │
└─────────────────────────────────────────────────────────────┘
```

## Nouveaux outils hybrides (v2)

### 1. `smart_references`

**Remplace/améliore**: `get_symbol_callers` + LSP `findReferences`

```python
# Utilisation
result = smart_references(db, "src/main.py", line=42, character=10)

# Retour enrichi
{
    "references": [
        {
            "file": "src/api.py",
            "line": 15,
            "criticality_score": 0.8,  # Score 0-1
            "error_count": 2,          # Erreurs historiques
            "git_activity": 5,         # Commits 30j
            "is_critical": true
        }
    ],
    "summary": {
        "total_references": 12,
        "critical_references": 3,
        "files_affected": 5
    }
}
```

### 2. `smart_callers`

**Remplace/améliore**: `get_symbol_callers` + LSP `incomingCalls`

```python
result = smart_callers(db, "src/core.py", line=100, character=5)

{
    "callers": {
        "critical": [
            {
                "name": "main",
                "file": "src/main.py",
                "error_history": [...],
                "patterns_violated": ["error_handling"]
            }
        ],
        "normal": [...]
    },
    "summary": {
        "total_callers": 8,
        "critical_callers": 2,
        "with_error_history": 3
    }
}
```

### 3. `impact_analysis_v2`

**Remplace/améliore**: `get_file_impact`

```python
result = impact_analysis_v2(db, "src/core.py", changes=["def foo():"])

{
    "file": "src/core.py",
    "risk_score": 72,              # Score 0-100
    "risk_factors": [
        "Critical file",
        "High reference count (25)",
        "Has error history (3)"
    ],
    "direct_references": [...],
    "call_hierarchy": [...],
    "historical_bugs": [...],
    "similar_changes": [...]       # Changements passés similaires
}
```

### 4. `smart_search`

**Remplace/améliore**: `search_symbols` + LSP `workspaceSymbol`

```python
result = smart_search(db, "init*", kind="function", include_metrics=True)

{
    "query": "init*",
    "results": [
        {
            "name": "init_app",
            "kind": "function",
            "file": "src/app.py",
            "is_critical": true,
            "metrics": {
                "lines": 45,
                "complexity": 8
            }
        }
    ],
    "total": 15,
    "source": "hybrid"  # lsp/agentdb/hybrid
}
```

### 5. `get_risk_assessment`

**Nouveau**: Évaluation de risque multi-fichiers

```python
result = get_risk_assessment(db, file_paths=["src/core.py", "src/api.py"])

{
    "files": [
        {"file": "src/core.py", "risk_score": 65, ...},
        {"file": "src/api.py", "risk_score": 20, ...}
    ],
    "overall_risk_score": 42.5,
    "risk_factors": ["Critical file", "High reference count"],
    "recommendations": [
        "Review critical files changes with extra care",
        "Run comprehensive tests"
    ]
}
```

## Migration des outils v1 vers v2

| Outil v1 | Outil v2 | Avantages |
|----------|----------|-----------|
| `get_symbol_callers` | `smart_callers` | + patterns, + erreurs, + séparation critiques |
| `get_symbol_callees` | LSP `outgoingCalls` direct | Plus rapide, plus précis |
| `search_symbols` | `smart_search` | + métriques, + source indiquée |
| `get_file_impact` | `impact_analysis_v2` | + risk_score, + recommandations |
| - | `get_risk_assessment` | Nouveau: analyse multi-fichiers |

## Stratégie de fallback

L'architecture hybride utilise une stratégie de fallback intelligente:

1. **LSP disponible**: Utilise LSP pour les requêtes rapides, enrichit avec AgentDB
2. **LSP non disponible**: Fallback complet sur AgentDB (plus lent mais fonctionnel)
3. **Erreur LSP**: Log l'erreur, continue avec AgentDB seul

```python
# Dans hybrid_lsp.py
def smart_references(self, file_path, line, character, ...):
    # 1. Essayer LSP d'abord
    lsp_refs = self.lsp.find_references(file_path, line, character)

    # 2. Fallback sur AgentDB si LSP vide
    if not lsp_refs:
        lsp_refs = self._fallback_references_from_agentdb(...)

    # 3. Enrichir avec contexte AgentDB
    for ref in lsp_refs:
        ref = self.enricher.enrich_reference(ref)

    return references
```

## Score de risque

Le score de risque (0-100) est calculé à partir de plusieurs facteurs:

| Facteur | Points | Condition |
|---------|--------|-----------|
| Fichier critique | +25 | `is_critical = true` |
| Beaucoup de références | +10-20 | > 10 ou > 20 références |
| Références critiques | +10-25 | Références depuis fichiers critiques |
| Historique d'erreurs | +10-20 | > 0 ou > 5 erreurs |
| Complexité élevée | +5-15 | > 10 ou > 20 cyclomatique |
| Activité récente (churn) | +10 | > 10 commits/30j |

## Fichiers créés/modifiés

```
.claude/agentdb/
├── hybrid_lsp.py          # NOUVEAU: Couche hybride LSP + AgentDB
├── HYBRID_ARCHITECTURE.md # NOUVEAU: Cette documentation
└── query.sh               # MODIFIÉ: Corrections injection SQL

.claude/mcp/agentdb/
├── tools_v2.py            # NOUVEAU: 5 outils hybrides
└── server.py              # MODIFIÉ: v2.0, 15 outils (10 + 5)
```

## Utilisation recommandée

### Pour l'analyse d'impact

```python
# Avant (v1)
impact = get_file_impact(db, "src/core.py")

# Après (v2) - Plus complet avec score de risque
impact = impact_analysis_v2(db, "src/core.py")
print(f"Risk score: {impact['risk_score']}/100")
print(f"Factors: {impact['risk_factors']}")
```

### Pour évaluer une PR

```python
# Nouveau (v2) - Analyse multi-fichiers
files = ["src/api.py", "src/db.py", "src/utils.py"]
assessment = get_risk_assessment(db, files)

if assessment["overall_risk_score"] > 70:
    print("HIGH RISK PR - Review carefully")
    for rec in assessment["recommendations"]:
        print(f"  - {rec}")
```

### Pour rechercher des symboles

```python
# Avant (v1)
results = search_symbols(db, "init*")

# Après (v2) - Avec métriques et source indiquée
results = smart_search(db, "init*", include_metrics=True)
print(f"Source: {results['source']}")  # hybrid/lsp/agentdb
```

## Compatibilité

- Les outils v1 restent disponibles et fonctionnels
- Les outils v2 sont préfixés `smart_` ou suffixés `_v2`
- Migration progressive recommandée
- Aucun breaking change pour les outils existants
