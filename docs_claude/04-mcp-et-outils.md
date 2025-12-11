# MCP et Outils

> Documentation technique complete des 10 outils MCP exposes par AgentDB

---

## Vue d'Ensemble du Protocole MCP

Le **Model Context Protocol (MCP)** est un protocole standardise permettant aux agents IA d'interagir avec des outils externes via JSON-RPC.

```
+------------------+          JSON-RPC          +------------------+
|   Agent IA       | <----------------------->  |   MCP Server     |
|   (Claude)       |    stdin/stdout (stdio)    |   AgentDB        |
+------------------+                            +------------------+
                                                        |
                                                        v
                                                +------------------+
                                                |   10 Outils      |
                                                |   tools.py       |
                                                +------------------+
```

---

## Liste des 10 Outils

| # | Outil | Categorie | Description |
|---|-------|-----------|-------------|
| 1 | `get_file_context` | Graphe | Contexte complet d'un fichier |
| 2 | `get_symbol_callers` | Graphe | Appelants d'un symbole |
| 3 | `get_symbol_callees` | Graphe | Symboles appeles |
| 4 | `get_file_impact` | Graphe | Impact d'une modification |
| 5 | `get_error_history` | Historique | Bugs et resolutions |
| 6 | `get_patterns` | Connaissance | Patterns applicables |
| 7 | `get_architecture_decisions` | Connaissance | ADRs applicables |
| 8 | `search_symbols` | Recherche | Recherche de symboles |
| 9 | `get_file_metrics` | Metriques | Metriques detaillees |
| 10 | `get_module_summary` | Metriques | Resume d'un module |

---

## Outil 1 : get_file_context

> L'outil le plus utilise - Vue 360 degres d'un fichier

### Signature

```python
get_file_context(
    path: str,
    include_symbols: bool = True,
    include_dependencies: bool = True,
    include_history: bool = True,
    include_patterns: bool = True
) -> dict
```

### Parametres

| Parametre | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | **requis** | Chemin du fichier relatif a la racine |
| `include_symbols` | bool | `true` | Inclure la liste des symboles |
| `include_dependencies` | bool | `true` | Inclure les dependances |
| `include_history` | bool | `true` | Inclure l'historique d'erreurs |
| `include_patterns` | bool | `true` | Inclure les patterns applicables |

### Exemple de Reponse

```json
{
  "file": {
    "path": "src/drivers/lcd.c",
    "module": "drivers",
    "language": "c",
    "is_critical": true,
    "security_sensitive": false,
    "metrics": {
      "lines_total": 450,
      "lines_code": 320,
      "lines_comment": 85,
      "complexity_avg": 4.2,
      "complexity_max": 12
    },
    "activity": {
      "commits_30d": 5,
      "commits_90d": 12,
      "last_modified": "2024-01-10T14:30:00Z",
      "contributors": ["alice", "bob"]
    }
  },
  "symbols": [
    {
      "name": "lcd_init",
      "kind": "function",
      "signature": "int lcd_init(lcd_config_t *config)",
      "complexity": 8,
      "has_doc": true,
      "line_start": 45,
      "line_end": 92
    },
    {
      "name": "lcd_write",
      "kind": "function",
      "signature": "int lcd_write(uint8_t *data, size_t len)",
      "complexity": 12,
      "has_doc": true,
      "line_start": 95,
      "line_end": 165
    }
  ],
  "dependencies": {
    "includes": ["drivers/gpio.h", "common/types.h"],
    "included_by": ["app/display.c", "tests/test_lcd.c"],
    "calls_to": ["gpio_set", "delay_ms", "spi_transfer"],
    "called_by": ["display_init", "display_refresh"]
  },
  "error_history": [
    {
      "type": "buffer_overflow",
      "severity": "critical",
      "title": "Buffer overflow in lcd_write",
      "resolved_at": "2023-11-15",
      "resolution": "Added bounds checking"
    }
  ],
  "patterns": [
    {
      "name": "driver_error_handling",
      "title": "Driver Error Handling",
      "description": "All driver functions must return error codes"
    }
  ],
  "architecture_decisions": [
    {
      "id": "ADR-003",
      "title": "SPI-based LCD Communication"
    }
  ]
}
```

---

## Outil 2 : get_symbol_callers

> Trouve tous les appelants d'un symbole (recursif)

### Signature

```python
get_symbol_callers(
    symbol_name: str,
    file_path: str = None,
    max_depth: int = 3,
    include_indirect: bool = True
) -> dict
```

### Parametres

| Parametre | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol_name` | string | **requis** | Nom du symbole |
| `file_path` | string | `null` | Fichier pour desambiguiser |
| `max_depth` | int | `3` | Profondeur max (1-10) |
| `include_indirect` | bool | `true` | Inclure appels via pointeurs |

### Exemple de Reponse

```json
{
  "symbol": {
    "name": "lcd_write",
    "file": "src/drivers/lcd.c",
    "kind": "function"
  },
  "callers": {
    "level_1": [
      {
        "name": "display_refresh",
        "file": "src/app/display.c",
        "line": 78,
        "is_direct": true
      },
      {
        "name": "display_clear",
        "file": "src/app/display.c",
        "line": 45,
        "is_direct": true
      }
    ],
    "level_2": [
      {
        "name": "ui_update",
        "file": "src/ui/render.c",
        "line": 120,
        "is_direct": true
      }
    ],
    "level_3": [
      {
        "name": "main_loop",
        "file": "src/main.c",
        "line": 55,
        "is_direct": true
      }
    ]
  },
  "summary": {
    "total_callers": 4,
    "max_depth_reached": 3,
    "critical_callers": 1,
    "files_affected": [
      "src/app/display.c",
      "src/ui/render.c",
      "src/main.c"
    ]
  }
}
```

### Cas d'Usage

- **Analyse d'impact** : Avant de modifier une fonction
- **Refactoring** : Identifier tous les sites d'appel
- **Documentation** : Comprendre l'utilisation d'une API

---

## Outil 3 : get_symbol_callees

> Trouve tous les symboles appeles par un symbole

### Signature

```python
get_symbol_callees(
    symbol_name: str,
    file_path: str = None,
    max_depth: int = 2
) -> dict
```

### Exemple de Reponse

```json
{
  "symbol": {
    "name": "lcd_init",
    "file": "src/drivers/lcd.c"
  },
  "callees": {
    "level_1": [
      {
        "name": "gpio_init",
        "file": "src/drivers/gpio.c",
        "kind": "function"
      },
      {
        "name": "spi_init",
        "file": "src/drivers/spi.c",
        "kind": "function"
      },
      {
        "name": "malloc",
        "file": "stdlib",
        "kind": "function",
        "external": true
      }
    ],
    "level_2": [
      {
        "name": "port_config",
        "file": "src/hal/port.c",
        "kind": "function"
      }
    ]
  },
  "types_used": [
    {
      "name": "lcd_config_t",
      "file": "src/drivers/lcd.h"
    },
    {
      "name": "gpio_pin_t",
      "file": "src/drivers/gpio.h"
    }
  ]
}
```

---

## Outil 4 : get_file_impact

> Calcule l'impact complet de la modification d'un fichier

### Signature

```python
get_file_impact(
    path: str,
    include_transitive: bool = True,
    max_depth: int = 3
) -> dict
```

### Exemple de Reponse

```json
{
  "file": "src/drivers/lcd.h",
  "direct_impact": [
    {
      "file": "src/drivers/lcd.c",
      "reason": "includes header",
      "symbols": ["lcd_init", "lcd_write"]
    },
    {
      "file": "src/app/display.c",
      "reason": "uses lcd_write",
      "symbols": ["display_refresh"]
    }
  ],
  "transitive_impact": [
    {
      "file": "src/ui/render.c",
      "reason": "calls display_refresh",
      "depth": 2
    },
    {
      "file": "src/main.c",
      "reason": "calls ui_update",
      "depth": 3
    }
  ],
  "include_impact": [
    {
      "file": "src/drivers/lcd.c",
      "reason": "includes src/drivers/lcd.h"
    },
    {
      "file": "tests/test_lcd.c",
      "reason": "includes src/drivers/lcd.h"
    }
  ],
  "summary": {
    "total_files_impacted": 5,
    "critical_files_impacted": 1,
    "max_depth": 3
  }
}
```

### Visualisation de l'Impact

```
lcd.h (modifie)
    |
    +-- lcd.c (direct - includes)
    |      |
    |      +-- display.c (direct - uses)
    |             |
    |             +-- render.c (depth 2)
    |                    |
    |                    +-- main.c (depth 3)
    |
    +-- test_lcd.c (include)
```

---

## Outil 5 : get_error_history

> Recupere l'historique des erreurs et bugs

### Signature

```python
get_error_history(
    file_path: str = None,
    symbol_name: str = None,
    module: str = None,
    error_type: str = None,
    severity: str = None,
    days: int = 180,
    limit: int = 20
) -> dict
```

### Parametres

| Parametre | Type | Description |
|-----------|------|-------------|
| `file_path` | string | Filtrer par fichier |
| `symbol_name` | string | Filtrer par symbole |
| `module` | string | Filtrer par module |
| `error_type` | string | Type d'erreur (voir tableau) |
| `severity` | string | Severite minimum |
| `days` | int | Periode en jours |
| `limit` | int | Nombre max de resultats |

### Types d'Erreurs

| Categorie | Types |
|-----------|-------|
| Memoire | `buffer_overflow`, `null_pointer`, `memory_leak`, `use_after_free` |
| Concurrence | `race_condition`, `deadlock` |
| Securite | `sql_injection`, `xss`, `command_injection` |
| Logique | `logic_error`, `integer_overflow`, `infinite_loop` |

### Exemple de Reponse

```json
{
  "query": {
    "file_path": "src/drivers/lcd.c",
    "severity": "high",
    "days": 365
  },
  "errors": [
    {
      "id": 42,
      "type": "buffer_overflow",
      "severity": "critical",
      "title": "Buffer overflow in lcd_write",
      "description": "Writing beyond buffer bounds when data > 256 bytes",
      "discovered_at": "2023-10-15",
      "resolved_at": "2023-10-16",
      "resolution": "Added size check: if (len > LCD_MAX_BUFFER) return -E_OVERFLOW",
      "prevention": "Always validate buffer sizes before write operations",
      "is_regression": false,
      "jira_ticket": "BUG-1234"
    }
  ],
  "statistics": {
    "total_errors": 1,
    "by_type": {
      "buffer_overflow": 1
    },
    "by_severity": {
      "critical": 1
    },
    "regression_rate": 0.0
  }
}
```

---

## Outil 6 : get_patterns

> Recupere les patterns de code applicables

### Signature

```python
get_patterns(
    file_path: str = None,
    module: str = None,
    category: str = None
) -> dict
```

### Exemple de Reponse

```json
{
  "applicable_patterns": [
    {
      "name": "driver_error_codes",
      "category": "error_handling",
      "title": "Driver Error Codes",
      "description": "All driver functions return standardized error codes",
      "severity": "error",
      "good_example": "int lcd_init(...) {\n  if (!config) return -E_NULL_PTR;\n  ...\n  return E_OK;\n}",
      "bad_example": "void lcd_init(...) {\n  // No error handling\n}"
    }
  ],
  "project_patterns": [
    {
      "name": "memory_safety_malloc",
      "category": "memory_safety",
      "title": "Safe Memory Allocation",
      "description": "Always check malloc return and free on all paths",
      "severity": "critical"
    }
  ]
}
```

---

## Outil 7 : get_architecture_decisions

> Recupere les decisions architecturales (ADR)

### Signature

```python
get_architecture_decisions(
    module: str = None,
    file_path: str = None,
    status: str = "accepted"
) -> dict
```

### Statuts ADR

| Statut | Description |
|--------|-------------|
| `proposed` | En discussion |
| `accepted` | Approuve et actif |
| `deprecated` | Obsolete mais historique |
| `superseded` | Remplace par un autre ADR |
| `rejected` | Refuse |

### Exemple de Reponse

```json
{
  "decisions": [
    {
      "id": "ADR-007",
      "title": "No Direct Hardware Access in Application Layer",
      "status": "accepted",
      "context": "Application code was directly accessing GPIO registers causing portability issues",
      "decision": "All hardware access must go through the HAL layer",
      "consequences": "Slight performance overhead, but improved testability and portability",
      "date_decided": "2023-06-15",
      "decided_by": "Tech Lead"
    }
  ]
}
```

---

## Outil 8 : search_symbols

> Recherche de symboles par pattern

### Signature

```python
search_symbols(
    query: str,
    kind: str = None,
    module: str = None,
    limit: int = 50
) -> dict
```

### Wildcards Supportes

| Pattern | Description | Exemple |
|---------|-------------|---------|
| `*` | Zero ou plusieurs caracteres | `lcd_*` -> `lcd_init`, `lcd_write` |
| `?` | Un seul caractere | `gpio_?et` -> `gpio_get`, `gpio_set` |

### Exemple de Reponse

```json
{
  "query": "lcd_*",
  "results": [
    {
      "name": "lcd_init",
      "kind": "function",
      "file": "src/drivers/lcd.c",
      "signature": "int lcd_init(lcd_config_t *config)",
      "line": 45
    },
    {
      "name": "lcd_write",
      "kind": "function",
      "file": "src/drivers/lcd.c",
      "signature": "int lcd_write(uint8_t *data, size_t len)",
      "line": 95
    },
    {
      "name": "lcd_config_t",
      "kind": "struct",
      "file": "src/drivers/lcd.h",
      "signature": null,
      "line": 12
    }
  ],
  "total": 3,
  "returned": 3
}
```

---

## Outil 9 : get_file_metrics

> Recupere les metriques detaillees d'un fichier

### Signature

```python
get_file_metrics(path: str) -> dict
```

### Exemple de Reponse

```json
{
  "file": "src/drivers/lcd.c",
  "size": {
    "lines_total": 450,
    "lines_code": 320,
    "lines_comment": 85,
    "lines_blank": 45,
    "bytes": 12560
  },
  "complexity": {
    "cyclomatic_total": 42,
    "cyclomatic_avg": 4.2,
    "cyclomatic_max": 12,
    "cognitive_total": 35,
    "nesting_max": 4
  },
  "structure": {
    "functions": 10,
    "types": 2,
    "macros": 5,
    "variables": 8
  },
  "quality": {
    "documentation_score": 75,
    "has_tests": true,
    "technical_debt_score": 25
  },
  "activity": {
    "commits_30d": 5,
    "commits_90d": 12,
    "commits_365d": 45,
    "contributors": ["alice", "bob", "charlie"],
    "last_modified": "2024-01-10T14:30:00Z",
    "age_days": 365
  }
}
```

---

## Outil 10 : get_module_summary

> Resume agrege d'un module complet

### Signature

```python
get_module_summary(module: str) -> dict
```

### Exemple de Reponse

```json
{
  "module": "drivers",
  "files": {
    "total": 15,
    "sources": 10,
    "headers": 5,
    "tests": 8,
    "critical": 3
  },
  "symbols": {
    "functions": 85,
    "types": 12,
    "macros": 25
  },
  "metrics": {
    "lines_total": 4500,
    "complexity_avg": 5.2,
    "documentation_score": 72
  },
  "health": {
    "errors_last_90d": 2,
    "test_coverage": "partial",
    "technical_debt": "low"
  },
  "patterns": ["driver_error_handling", "memory_safety"],
  "adrs": ["ADR-003", "ADR-007"],
  "dependencies": {
    "depends_on": ["hal", "common"],
    "depended_by": ["app", "ui"]
  }
}
```

---

## Gestion des Erreurs

Tous les outils retournent un champ `error` en cas de probleme :

```json
{
  "error": "File not found: src/unknown.c"
}
```

### Codes d'Erreur Courants

| Message | Cause | Solution |
|---------|-------|----------|
| `File not found` | Chemin invalide | Verifier le path |
| `Symbol not found` | Symbole inexistant | Verifier le nom |
| `Database error` | Erreur SQLite | Verifier l'integrite DB |
| `Timeout` | Requete trop lente | Reduire max_depth |

---

## Prochaine Etape

Continuez vers [05-guide-lineaire.md](./05-guide-lineaire.md) pour un tutoriel pas a pas d'utilisation complete.
