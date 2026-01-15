# AgentDB Multi-Language Support (v4.0)

## Vue d'ensemble

AgentDB v4.0 introduit le support multi-langage via **tree-sitter**, un générateur de parsers et bibliothèque d'analyse incrémentale.

```
┌─────────────────────────────────────────────────────────────┐
│                    TREE-SITTER PARSER                        │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Python  │  │    Go    │  │   Rust   │  │   Java   │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │             │             │             │           │
│       └─────────────┴─────────────┴─────────────┘           │
│                           │                                  │
│                           ▼                                  │
│              ┌────────────────────────┐                     │
│              │   ParseResult unifié   │                     │
│              │  - symbols[]           │                     │
│              │  - imports[]           │                     │
│              │  - calls[]             │                     │
│              └────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

## Langages supportés

### Tier 1 - Support complet
| Langage | Extensions | Symboles | Imports | Appels |
|---------|------------|----------|---------|--------|
| Python | `.py`, `.pyw`, `.pyi` | ✅ | ✅ | ✅ |
| JavaScript | `.js`, `.jsx`, `.mjs`, `.cjs` | ✅ | ✅ | ✅ |
| TypeScript | `.ts`, `.tsx` | ✅ | ✅ | ✅ |
| Go | `.go` | ✅ | ✅ | ✅ |
| Rust | `.rs` | ✅ | ✅ | ✅ |
| C | `.c`, `.h` | ✅ | ✅ | ✅ |
| C++ | `.cpp`, `.cc`, `.cxx`, `.hpp` | ✅ | ✅ | ✅ |
| Java | `.java` | ✅ | ✅ | ✅ |

### Tier 2 - Support basique
| Langage | Extensions | Symboles | Imports | Appels |
|---------|------------|----------|---------|--------|
| Ruby | `.rb`, `.rake` | ✅ | ⚠️ | ⚠️ |
| PHP | `.php` | ✅ | ⚠️ | ⚠️ |
| Kotlin | `.kt`, `.kts` | ✅ | ⚠️ | ⚠️ |
| Swift | `.swift` | ✅ | ⚠️ | ⚠️ |
| Scala | `.scala` | ✅ | ⚠️ | ⚠️ |
| C# | `.cs` | ✅ | ⚠️ | ⚠️ |

### Tier 3 - Support minimal
| Langage | Extensions | Notes |
|---------|------------|-------|
| Bash | `.sh`, `.bash` | Fonctions uniquement |
| SQL | `.sql` | Structure basique |
| YAML | `.yml`, `.yaml` | Clés de niveau supérieur |
| JSON | `.json` | Clés de niveau supérieur |
| TOML | `.toml` | Sections et clés |

## Installation

```bash
# Installer tree-sitter avec les grammaires pré-compilées
pip install tree-sitter-languages

# Vérifier l'installation
python -c "import tree_sitter_languages; print('OK')"
```

## Utilisation

### Via l'outil MCP `parse_file`

```json
{
  "name": "parse_file",
  "arguments": {
    "file_path": "src/main.go",
    "include_calls": true,
    "include_imports": true
  }
}
```

### Réponse

```json
{
  "file_path": "src/main.go",
  "language": "go",
  "symbols": [
    {
      "name": "main",
      "kind": "function",
      "line_start": 10,
      "line_end": 25,
      "signature": "()",
      "visibility": "private"
    },
    {
      "name": "Config",
      "kind": "struct",
      "line_start": 5,
      "line_end": 8
    }
  ],
  "imports": [
    {"module": "fmt", "line": 3},
    {"module": "os", "line": 4}
  ],
  "calls": [
    {"name": "Println", "line": 12, "is_method": true, "receiver": "fmt"}
  ],
  "stats": {
    "symbol_count": 2,
    "import_count": 2,
    "call_count": 1,
    "parse_time_ms": 5.2
  }
}
```

### Via Python directement

```python
from agentdb.tree_sitter_parser import parse_file, parse_content

# Parser un fichier
result = parse_file("src/main.go")
print(f"Found {len(result.symbols)} symbols")

# Parser du contenu directement
code = '''
def hello(name: str) -> str:
    """Says hello."""
    return f"Hello, {name}!"
'''
result = parse_content(code, "python")
for sym in result.symbols:
    print(f"{sym.kind}: {sym.name} at line {sym.line_start}")
```

## Types de symboles extraits

### Python
- `function` - Fonctions de niveau module
- `class` - Classes
- `method` - Méthodes de classe
- `property` - Propriétés (@property)

### JavaScript/TypeScript
- `function` - Fonctions déclarées
- `class` - Classes
- `method` - Méthodes
- `interface` - Interfaces (TS)
- `type` - Type aliases (TS)

### Go
- `function` - Fonctions
- `method` - Méthodes (avec receiver)
- `type` - Déclarations de type
- `struct` - Structures

### Rust
- `function` - Fonctions
- `struct` - Structures
- `enum` - Énumérations
- `trait` - Traits
- `impl` - Implémentations

### C/C++
- `function` - Fonctions
- `struct` - Structures
- `class` - Classes (C++)
- `enum` - Énumérations
- `namespace` - Namespaces (C++)

### Java
- `method` - Méthodes
- `class` - Classes
- `interface` - Interfaces
- `enum` - Énumérations
- `constructor` - Constructeurs

## Fallback

Si tree-sitter n'est pas disponible, AgentDB utilise des fallbacks :

1. **Python** : Module `ast` natif (complet)
2. **C/C++** : `ctags` si installé
3. **Autres** : Pas d'extraction de symboles

## Métriques calculées

Pour chaque symbole, tree-sitter extrait :

| Métrique | Description |
|----------|-------------|
| `line_start` | Ligne de début |
| `line_end` | Ligne de fin |
| `complexity` | Complexité cyclomatique estimée |
| `visibility` | public/private/protected |
| `signature` | Signature de fonction/méthode |
| `doc_comment` | Documentation extraite |
| `base_classes` | Classes parentes (héritage) |

## Intégration avec bootstrap.py

Le bootstrap utilise automatiquement tree-sitter quand disponible :

```bash
# Indexation avec tree-sitter (si disponible)
python .claude/scripts/bootstrap.py --full

# Le step 4 utilise tree-sitter pour tous les langages supportés
# Step 4/10: Indexing symbols and relations...
#   ✓ tree-sitter available (multi-language support)
```

## Comparaison avec les autres parsers

| Feature | tree-sitter | ctags | Python ast |
|---------|-------------|-------|------------|
| Multi-langage | ✅ 15+ | ✅ 40+ | ❌ Python |
| Précision AST | ✅ Parfait | ⚠️ Regex | ✅ Parfait |
| Appels | ✅ | ❌ | ✅ |
| Imports | ✅ | ⚠️ | ✅ |
| Visibilité | ✅ | ⚠️ | ✅ |
| Complexité | ✅ | ❌ | ✅ |
| Incrémental | ✅ | ❌ | ❌ |
| Performance | ✅ Rapide | ✅ Rapide | ✅ Rapide |

## Fichiers créés

```
.claude/agentdb/
├── tree_sitter_parser.py    # Module principal
├── MULTILANG_SUPPORT.md     # Cette documentation
└── schema.sql               # Inchangé (symboles compatibles)

.claude/mcp/agentdb/
└── server.py                # v4.0 avec 2 nouveaux outils
```

## Nouveaux outils MCP (v4)

1. **`parse_file`** - Parse un fichier avec tree-sitter
2. **`get_supported_languages`** - Liste les langages supportés

Total : **20 outils MCP** (10 v1 + 5 v2 + 3 v3 + 2 v4)
