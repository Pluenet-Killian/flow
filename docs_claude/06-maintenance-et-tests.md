# Maintenance et Tests

> Validation du systeme, procedures de maintenance et bonnes pratiques operationnelles

---

## Vue d'Ensemble de la Suite de Tests

La suite de tests AgentDB couvre toutes les couches du systeme :

```
.claude/tests/
├── __init__.py
├── conftest.py          # Fixtures partageees
├── test_crud.py         # Tests des repositories
├── test_db.py           # Tests de la base
├── test_mcp_tools.py    # Tests des outils MCP
├── test_models.py       # Tests des modeles
└── test_queries.py      # Tests des requetes graphe
```

### Statistiques de la Suite

| Fichier | Lignes | Couverture |
|---------|--------|------------|
| `test_crud.py` | ~800 | Operations CRUD |
| `test_db.py` | ~400 | Connexion, transactions |
| `test_mcp_tools.py` | ~600 | 10 outils MCP |
| `test_models.py` | ~500 | Modeles, serialization |
| `test_queries.py` | ~700 | Traversee graphe |
| **Total** | ~3,000+ | Complet |

---

## Execution des Tests

### Lancer Tous les Tests

```bash
cd .claude
pytest tests/ -v
```

### Lancer un Fichier Specifique

```bash
# Tests des outils MCP uniquement
pytest tests/test_mcp_tools.py -v

# Tests des requetes graphe
pytest tests/test_queries.py -v
```

### Lancer un Test Specifique

```bash
# Test d'un outil MCP
pytest tests/test_mcp_tools.py::test_get_file_context -v

# Test avec pattern
pytest tests/ -k "callers" -v
```

### Options Utiles

| Option | Description |
|--------|-------------|
| `-v` | Mode verbose |
| `-x` | S'arreter au premier echec |
| `-s` | Afficher les prints |
| `--tb=short` | Traceback court |
| `-k "pattern"` | Filtrer par nom |
| `--cov=agentdb` | Rapport de couverture |

---

## Fixtures de Test (`conftest.py`)

### Fixture : Base de Donnees en Memoire

```python
@pytest.fixture
def db():
    """Cree une base de donnees en memoire pour les tests."""
    database = Database(":memory:")
    database.execute_script(SCHEMA_SQL)
    yield database
    database.close()
```

### Fixture : Donnees de Test

```python
@pytest.fixture
def sample_file(db):
    """Insere un fichier de test."""
    file_repo = FileRepository(db)
    file_id = file_repo.insert(
        path="src/test.c",
        module="test",
        language="c",
        lines_total=100,
        lines_code=80,
    )
    return file_id

@pytest.fixture
def sample_symbols(db, sample_file):
    """Insere des symboles de test."""
    symbol_repo = SymbolRepository(db)
    symbols = [
        {"name": "func_a", "kind": "function", "file_id": sample_file},
        {"name": "func_b", "kind": "function", "file_id": sample_file},
        {"name": "struct_x", "kind": "struct", "file_id": sample_file},
    ]
    ids = [symbol_repo.insert(**s) for s in symbols]
    return ids
```

---

## Tests par Categorie

### 1. Tests CRUD (`test_crud.py`)

Verifie les operations de base sur chaque repository.

```python
class TestFileRepository:
    """Tests pour FileRepository."""

    def test_insert_file(self, db):
        """Insertion d'un fichier."""
        repo = FileRepository(db)
        file_id = repo.insert(
            path="src/main.c",
            module="core",
            language="c"
        )
        assert file_id > 0

    def test_find_by_path(self, db, sample_file):
        """Recherche par chemin."""
        repo = FileRepository(db)
        file = repo.find_by_path("src/test.c")
        assert file is not None
        assert file.path == "src/test.c"

    def test_update_metrics(self, db, sample_file):
        """Mise a jour des metriques."""
        repo = FileRepository(db)
        repo.update_metrics(
            sample_file,
            lines_code=100,
            complexity_avg=5.0
        )
        file = repo.get_by_id(sample_file)
        assert file.lines_code == 100
        assert file.complexity_avg == 5.0

    def test_delete_cascade(self, db, sample_file, sample_symbols):
        """Suppression en cascade des symboles."""
        file_repo = FileRepository(db)
        symbol_repo = SymbolRepository(db)

        file_repo.delete(sample_file)

        # Verifier que les symboles sont supprimes
        for sym_id in sample_symbols:
            assert symbol_repo.get_by_id(sym_id) is None
```

### 2. Tests Base (`test_db.py`)

Verifie les fonctionnalites bas niveau.

```python
class TestDatabase:
    """Tests pour la classe Database."""

    def test_connection(self):
        """Test de connexion basique."""
        db = Database(":memory:")
        assert db.is_connected()
        db.close()

    def test_transaction_commit(self, db):
        """Transaction avec commit."""
        with db.transaction():
            db.execute("INSERT INTO files (path) VALUES (?)", ("test.c",))

        row = db.fetch_one("SELECT path FROM files")
        assert row["path"] == "test.c"

    def test_transaction_rollback(self, db):
        """Transaction avec rollback."""
        try:
            with db.transaction():
                db.execute("INSERT INTO files (path) VALUES (?)", ("test.c",))
                raise ValueError("Erreur simulee")
        except ValueError:
            pass

        row = db.fetch_one("SELECT path FROM files")
        assert row is None

    def test_wal_mode(self, tmp_path):
        """Verification du mode WAL."""
        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.execute_script(SCHEMA_SQL)

        result = db.fetch_one("PRAGMA journal_mode;")
        assert result["journal_mode"] == "wal"

    def test_integrity_check(self, db):
        """Verification d'integrite."""
        manager = DatabaseManager(db)
        is_valid, errors = manager.check_integrity()
        assert is_valid
        assert errors == []
```

### 3. Tests Outils MCP (`test_mcp_tools.py`)

Verifie chaque outil MCP.

```python
class TestGetFileContext:
    """Tests pour get_file_context."""

    def test_basic_context(self, db, sample_file):
        """Contexte basique d'un fichier."""
        result = get_file_context(db, "src/test.c")

        assert "file" in result
        assert result["file"]["path"] == "src/test.c"
        assert result["file"]["language"] == "c"

    def test_with_symbols(self, db, sample_file, sample_symbols):
        """Contexte avec symboles."""
        result = get_file_context(db, "src/test.c", include_symbols=True)

        assert "symbols" in result
        assert len(result["symbols"]) == 3

    def test_file_not_found(self, db):
        """Fichier inexistant."""
        result = get_file_context(db, "nonexistent.c")
        assert "error" in result


class TestGetSymbolCallers:
    """Tests pour get_symbol_callers."""

    def test_direct_callers(self, db, sample_file, sample_symbols):
        """Appelants directs."""
        # Setup: func_a appelle func_b
        rel_repo = RelationRepository(db)
        rel_repo.insert(
            source_id=sample_symbols[0],  # func_a
            target_id=sample_symbols[1],  # func_b
            relation_type="calls"
        )

        result = get_symbol_callers(db, "func_b", "src/test.c")

        assert "callers" in result
        assert len(result["callers"]["level_1"]) == 1
        assert result["callers"]["level_1"][0]["name"] == "func_a"

    def test_recursive_callers(self, db, setup_call_chain):
        """Appelants recursifs (profondeur 3)."""
        # main -> display_update -> lcd_write
        result = get_symbol_callers(
            db, "lcd_write",
            max_depth=3
        )

        assert result["summary"]["total_callers"] >= 2
        assert result["summary"]["max_depth_reached"] == 2


class TestSearchSymbols:
    """Tests pour search_symbols."""

    def test_wildcard_search(self, db, sample_symbols):
        """Recherche avec wildcard."""
        result = search_symbols(db, "func_*")

        assert result["total"] == 2
        assert all(s["name"].startswith("func_") for s in result["results"])

    def test_filter_by_kind(self, db, sample_symbols):
        """Filtrage par type."""
        result = search_symbols(db, "*", kind="struct")

        assert result["total"] == 1
        assert result["results"][0]["name"] == "struct_x"
```

### 4. Tests Modeles (`test_models.py`)

Verifie les dataclasses et la serialization.

```python
class TestFileModel:
    """Tests pour le modele File."""

    def test_from_row(self):
        """Creation depuis une ligne DB."""
        row = {
            "id": 1,
            "path": "src/main.c",
            "module": "core",
            "language": "c",
            "is_critical": 1,
            "lines_code": 100,
        }
        file = File.from_row(row)

        assert file.id == 1
        assert file.path == "src/main.c"
        assert file.is_critical == True

    def test_to_dict(self):
        """Serialization en dict."""
        file = File(
            id=1,
            path="src/main.c",
            module="core"
        )
        d = file.to_dict()

        assert d["path"] == "src/main.c"
        assert "id" in d


class TestSymbolKindEnum:
    """Tests pour l'enum SymbolKind."""

    def test_valid_kinds(self):
        """Types valides."""
        assert SymbolKind.FUNCTION.value == "function"
        assert SymbolKind.STRUCT.value == "struct"
        assert SymbolKind.CLASS.value == "class"

    def test_from_string(self):
        """Conversion depuis string."""
        kind = SymbolKind("function")
        assert kind == SymbolKind.FUNCTION
```

### 5. Tests Requetes Graphe (`test_queries.py`)

Verifie la traversee du graphe de dependances.

```python
class TestGetSymbolCallersQuery:
    """Tests pour la requete get_symbol_callers."""

    def test_depth_limit(self, db, deep_call_chain):
        """Respect de la limite de profondeur."""
        # Chain: a -> b -> c -> d -> e
        result = get_symbol_callers(db, symbol_id=5, max_depth=2)

        assert result["summary"]["max_depth_reached"] == 2
        # Ne devrait pas inclure 'a' (depth 4)

    def test_cycle_detection(self, db, cyclic_calls):
        """Detection des cycles."""
        # a -> b -> c -> a (cycle)
        result = get_symbol_callers(db, symbol_id=1, max_depth=10)

        # Ne doit pas boucler indefiniment
        assert result["summary"]["total_callers"] == 2


class TestGetFileImpact:
    """Tests pour l'analyse d'impact."""

    def test_direct_impact(self, db, file_with_includers):
        """Impact direct via includes."""
        result = get_file_impact(db, "src/common.h")

        assert len(result["include_impact"]) > 0

    def test_transitive_impact(self, db, complex_dependencies):
        """Impact transitif."""
        result = get_file_impact(
            db, "src/lib.h",
            include_transitive=True,
            max_depth=3
        )

        assert len(result["transitive_impact"]) > 0
        assert result["summary"]["max_depth"] <= 3
```

---

## Couverture de Code

### Generer le Rapport

```bash
pytest tests/ --cov=agentdb --cov-report=html
```

### Consulter le Rapport

```bash
open htmlcov/index.html
```

### Objectifs de Couverture

| Module | Objectif | Priorite |
|--------|----------|----------|
| `crud.py` | > 90% | Critique |
| `queries.py` | > 85% | Critique |
| `tools.py` | > 80% | Haute |
| `db.py` | > 75% | Moyenne |
| `indexer.py` | > 70% | Moyenne |

---

## Procedures de Maintenance

### Maintenance Quotidienne

```bash
# Mise a jour incrementale (apres commits)
python .claude/scripts/update.py
```

### Maintenance Hebdomadaire

```bash
# 1. Vacuum de la base (recuperer l'espace)
sqlite3 .claude/agentdb/db.sqlite "VACUUM;"

# 2. Verification d'integrite
sqlite3 .claude/agentdb/db.sqlite "PRAGMA integrity_check;"

# 3. Mise a jour des statistiques SQLite
sqlite3 .claude/agentdb/db.sqlite "ANALYZE;"
```

### Maintenance Mensuelle

```bash
# 1. Nettoyage des vieux snapshots
sqlite3 .claude/agentdb/db.sqlite "
  DELETE FROM snapshot_symbols
  WHERE created_at < datetime('now', '-30 days');
"

# 2. Nettoyage des vieux runs
sqlite3 .claude/agentdb/db.sqlite "
  DELETE FROM pipeline_runs
  WHERE started_at < datetime('now', '-90 days')
  AND id NOT IN (SELECT id FROM pipeline_runs ORDER BY started_at DESC LIMIT 100);
"

# 3. Verification des foreign keys
sqlite3 .claude/agentdb/db.sqlite "PRAGMA foreign_key_check;"

# 4. Rotation des logs
ls -la .claude/logs/
# Supprimer les logs > 30 jours
find .claude/logs/ -name "*.log" -mtime +30 -delete
```

---

## Script de Maintenance Automatise

Le fichier `scripts/maintenance.py` automatise ces taches :

```bash
# Lancer la maintenance complete
python .claude/scripts/maintenance.py --full

# Options disponibles
python .claude/scripts/maintenance.py --help
```

### Options du Script

| Option | Description |
|--------|-------------|
| `--vacuum` | VACUUM de la base |
| `--analyze` | ANALYZE des statistiques |
| `--cleanup` | Nettoyage des vieilles donnees |
| `--integrity` | Verification d'integrite |
| `--full` | Toutes les operations |
| `--dry-run` | Afficher sans executer |

---

## Monitoring

### Metriques de Sante

```sql
-- Taille des tables
SELECT
    name,
    (SELECT COUNT(*) FROM files) as files_count,
    (SELECT COUNT(*) FROM symbols) as symbols_count,
    (SELECT COUNT(*) FROM relations) as relations_count,
    (SELECT COUNT(*) FROM error_history) as errors_count
FROM agentdb_meta WHERE key = 'schema_version';
```

### Performance des Requetes

```sql
-- Activer le profiling
.timer on

-- Executer une requete type
SELECT * FROM v_symbols_with_context
WHERE file_module = 'drivers' LIMIT 100;
```

### Alertes Recommandees

| Metrique | Seuil Warning | Seuil Critique |
|----------|---------------|----------------|
| Taille DB | > 100 MB | > 500 MB |
| Requete lente | > 100 ms | > 500 ms |
| Relations/fichier | > 1000 | > 5000 |
| Erreurs integrite | > 0 | > 0 |

---

## Sauvegarde et Restauration

### Sauvegarde

```bash
# Backup avec timestamp
BACKUP_FILE="agentdb_$(date +%Y%m%d_%H%M%S).sqlite"
sqlite3 .claude/agentdb/db.sqlite ".backup $BACKUP_FILE"

# Compresser
gzip $BACKUP_FILE
```

### Restauration

```bash
# Decompresser
gunzip agentdb_20240115_120000.sqlite.gz

# Restaurer
cp agentdb_20240115_120000.sqlite .claude/agentdb/db.sqlite
```

### Verification Post-Restauration

```bash
# Verifier l'integrite
sqlite3 .claude/agentdb/db.sqlite "PRAGMA integrity_check;"

# Verifier la version du schema
sqlite3 .claude/agentdb/db.sqlite "
  SELECT value FROM agentdb_meta WHERE key = 'schema_version';
"
```

---

## Troubleshooting

### Probleme : Base Corrompue

```bash
# Symptome : PRAGMA integrity_check retourne des erreurs

# Solution : Reconstruire
sqlite3 .claude/agentdb/db.sqlite ".dump" > backup.sql
rm .claude/agentdb/db.sqlite
sqlite3 .claude/agentdb/db.sqlite < backup.sql
```

### Probleme : Index Desynchronise

```bash
# Symptome : Symboles manquants apres modifications

# Solution : Reindexer le fichier
python -c "
from agentdb.indexer import CodeIndexer
from agentdb.db import get_database

db = get_database()
indexer = CodeIndexer(db)
indexer.reindex_file('src/problematic_file.c')
"
```

### Probleme : Performance Degradee

```bash
# Diagnostiquer
sqlite3 .claude/agentdb/db.sqlite "
  EXPLAIN QUERY PLAN
  SELECT * FROM symbols WHERE name LIKE 'lcd%';
"

# Solution : Reconstruire les index
sqlite3 .claude/agentdb/db.sqlite "REINDEX;"
```

---

## Checklist de Validation

Avant chaque release, verifier :

- [ ] Tous les tests passent : `pytest tests/ -v`
- [ ] Couverture > 80% : `pytest --cov=agentdb`
- [ ] Pas de regressions de performance
- [ ] Integrite de la base OK
- [ ] Documentation a jour

---

## Conclusion

Cette documentation couvre l'ensemble du systeme AgentDB :

1. **Introduction** : Vision et philosophie
2. **Architecture** : Composants et flux
3. **Configuration** : Parametrage complet
4. **Outils MCP** : 10 outils documentes
5. **Guide** : Tutoriel pas a pas
6. **Maintenance** : Tests et operations

Pour toute question, consultez les issues du projet ou la documentation inline dans le code.

---

## Liens Utiles

| Ressource | Chemin |
|-----------|--------|
| Schema SQL | `.claude/agentdb/schema.sql` |
| Configuration | `.claude/config/agentdb.yaml` |
| Logs | `.claude/logs/` |
| Tests | `.claude/tests/` |
