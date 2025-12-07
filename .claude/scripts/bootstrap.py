#!/usr/bin/env python3
"""
AgentDB Bootstrap Script - Initialisation de la base de données.

Ce script exécute les 9 étapes du bootstrap :
1. Créer la structure (dossiers)
2. Initialiser le schéma SQL
3. Scanner les fichiers
4. Indexer les symboles et relations
5. Calculer les métriques
6. Analyser l'activité Git
7. Marquer les fichiers critiques
8. Importer les patterns par défaut
9. Vérifier l'intégrité

Usage:
    python -m scripts.bootstrap [--project-root PATH]
    python .claude/scripts/bootstrap.py [--project-root PATH]
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# =============================================================================
# CONFIGURATION
# =============================================================================

# Couleurs pour le terminal
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"


# Désactiver les couleurs si pas de TTY
if not sys.stdout.isatty():
    for attr in dir(Colors):
        if not attr.startswith("_"):
            setattr(Colors, attr, "")


@dataclass
class BootstrapConfig:
    """Configuration du bootstrap."""
    project_root: Path
    claude_dir: Path
    agentdb_dir: Path
    db_path: Path
    schema_path: Path
    config_path: Path
    logs_dir: Path

    # Extensions par langage
    extensions: dict[str, list[str]] = field(default_factory=lambda: {
        "c": [".c", ".h"],
        "cpp": [".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx"],
        "python": [".py", ".pyi"],
        "javascript": [".js", ".jsx", ".mjs"],
        "typescript": [".ts", ".tsx"],
        "rust": [".rs"],
        "go": [".go"],
    })

    # Patterns à exclure
    exclude_patterns: list[str] = field(default_factory=lambda: [
        "build/**", "dist/**", "out/**", "target/**",
        "*.o", "*.obj", "*.exe", "*.dll", "*.so", "*.a",
        "vendor/**", "node_modules/**", ".venv/**", "venv/**",
        "__pycache__/**", "*.pyc", "*.egg-info/**",
        ".git/**", ".svn/**", ".idea/**", ".vscode/**",
        "*.swp", "*~",
        "**/*.min.js", "**/*.min.css", "**/*.generated.*",
        "**/generated/**",
        ".claude/agentdb/**",
        "coverage/**", ".coverage", ".pytest_cache/**",
    ])

    # Chemins critiques
    critical_paths: list[str] = field(default_factory=lambda: [
        "**/security/**", "**/auth/**", "**/authentication/**",
        "**/crypto/**", "**/encryption/**",
        "**/*password*", "**/*secret*", "**/*token*",
        "**/*credential*", "**/*key*",
        "**/main.*", "**/init.*", "**/bootstrap.*",
        "**/migration*", "**/schema*",
    ])

    # Chemins haute importance
    high_importance_paths: list[str] = field(default_factory=lambda: [
        "**/core/**", "**/kernel/**", "**/api/**",
        "**/services/**", "**/models/**", "**/handlers/**",
    ])

    @classmethod
    def from_project_root(cls, project_root: Path) -> "BootstrapConfig":
        """Crée une configuration à partir de la racine du projet."""
        claude_dir = project_root / ".claude"
        return cls(
            project_root=project_root,
            claude_dir=claude_dir,
            agentdb_dir=claude_dir / "agentdb",
            db_path=claude_dir / "agentdb" / "db.sqlite",
            schema_path=claude_dir / "agentdb" / "schema.sql",
            config_path=claude_dir / "config" / "agentdb.yaml",
            logs_dir=claude_dir / "logs",
        )


@dataclass
class BootstrapStats:
    """Statistiques du bootstrap."""
    files_scanned: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    symbols_indexed: int = 0
    relations_indexed: int = 0
    file_relations_indexed: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    start_time: float = 0
    end_time: float = 0

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time


# =============================================================================
# PROGRESS BAR
# =============================================================================

class ProgressBar:
    """Barre de progression simple."""

    def __init__(self, total: int, description: str = "", width: int = 40):
        self.total = max(total, 1)
        self.current = 0
        self.description = description
        self.width = width
        self.start_time = time.time()

    def update(self, n: int = 1) -> None:
        """Met à jour la progression."""
        self.current = min(self.current + n, self.total)
        self._render()

    def _render(self) -> None:
        """Affiche la barre de progression."""
        if not sys.stdout.isatty():
            return

        percent = self.current / self.total
        filled = int(self.width * percent)
        bar = "█" * filled + "░" * (self.width - filled)

        elapsed = time.time() - self.start_time
        if self.current > 0:
            eta = (elapsed / self.current) * (self.total - self.current)
            eta_str = f"ETA: {eta:.0f}s"
        else:
            eta_str = ""

        line = f"\r{Colors.CYAN}{self.description}{Colors.RESET} |{bar}| {self.current}/{self.total} ({percent:.0%}) {eta_str}  "
        sys.stdout.write(line)
        sys.stdout.flush()

    def finish(self) -> None:
        """Termine la barre de progression."""
        self.current = self.total
        self._render()
        if sys.stdout.isatty():
            print()


# =============================================================================
# LOGGER
# =============================================================================

def setup_logging(logs_dir: Path) -> logging.Logger:
    """Configure le logging."""
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("agentdb.bootstrap")
    logger.setLevel(logging.DEBUG)

    # File handler
    log_file = logs_dir / "bootstrap.log"
    fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    ))
    logger.addHandler(fh)

    # Console handler (warnings and errors only)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(ch)

    return logger


# =============================================================================
# STEP 1: CREATE STRUCTURE
# =============================================================================

def step_1_create_structure(config: BootstrapConfig, logger: logging.Logger) -> bool:
    """Étape 1 : Créer la structure de dossiers."""
    print(f"\n{Colors.BOLD}Step 1/9:{Colors.RESET} Creating directory structure...")

    directories = [
        config.agentdb_dir,
        config.claude_dir / "mcp" / "agentdb",
        config.claude_dir / "config",
        config.logs_dir,
        config.claude_dir / "scripts",
    ]

    for d in directories:
        d.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created directory: {d}")

    # Créer __init__.py si nécessaire
    init_files = [
        config.claude_dir / "mcp" / "__init__.py",
        config.claude_dir / "mcp" / "agentdb" / "__init__.py",
        config.agentdb_dir / "__init__.py",
        config.claude_dir / "scripts" / "__init__.py",
    ]

    for init_file in init_files:
        if not init_file.exists():
            init_file.write_text('"""AgentDB module."""\n')
            logger.debug(f"Created: {init_file}")

    print(f"  {Colors.GREEN}✓{Colors.RESET} Directory structure created")
    return True


# =============================================================================
# STEP 2: INITIALIZE SCHEMA
# =============================================================================

def step_2_init_schema(config: BootstrapConfig, logger: logging.Logger) -> bool:
    """Étape 2 : Initialiser le schéma SQL."""
    print(f"\n{Colors.BOLD}Step 2/9:{Colors.RESET} Initializing database schema...")

    # Vérifier que le schéma existe
    if not config.schema_path.exists():
        logger.error(f"Schema file not found: {config.schema_path}")
        print(f"  {Colors.RED}✗{Colors.RESET} Schema file not found: {config.schema_path}")
        return False

    # Supprimer l'ancienne base si elle existe
    if config.db_path.exists():
        backup_path = config.db_path.with_suffix(".sqlite.bak")
        shutil.copy(config.db_path, backup_path)
        config.db_path.unlink()
        logger.info(f"Backed up existing database to {backup_path}")

    # Créer la nouvelle base
    try:
        conn = sqlite3.connect(str(config.db_path))
        schema_sql = config.schema_path.read_text(encoding="utf-8")
        conn.executescript(schema_sql)
        conn.commit()

        # Vérifier les tables créées
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        conn.close()

        logger.info(f"Created database with tables: {tables}")
        print(f"  {Colors.GREEN}✓{Colors.RESET} Database created with {len(tables)} tables")
        return True

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        print(f"  {Colors.RED}✗{Colors.RESET} Database error: {e}")
        return False


# =============================================================================
# STEP 3: SCAN FILES
# =============================================================================

def should_exclude(path: str, patterns: list[str]) -> bool:
    """Vérifie si un chemin doit être exclu."""
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        # Support des patterns avec **
        if "**" in pattern:
            regex = pattern.replace("**", ".*").replace("*", "[^/]*")
            if re.match(regex, path):
                return True
    return False


def get_language(ext: str, extensions: dict[str, list[str]]) -> Optional[str]:
    """Détermine le langage à partir de l'extension."""
    for lang, exts in extensions.items():
        if ext.lower() in exts:
            return lang
    return None


def count_lines(file_path: Path) -> dict[str, int]:
    """Compte les lignes d'un fichier."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")

        total = len(lines)
        blank = sum(1 for line in lines if not line.strip())

        # Estimation simple des commentaires
        comment = 0
        in_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("/*"):
                in_block = True
            if in_block:
                comment += 1
                if "*/" in stripped:
                    in_block = False
            elif stripped.startswith("//") or stripped.startswith("#"):
                comment += 1

        code = total - blank - comment
        return {
            "total": total,
            "code": max(0, code),
            "comment": comment,
            "blank": blank,
        }
    except Exception:
        return {"total": 0, "code": 0, "comment": 0, "blank": 0}


def get_content_hash(file_path: Path) -> str:
    """Calcule le hash MD5 du contenu."""
    try:
        content = file_path.read_bytes()
        return hashlib.md5(content).hexdigest()
    except Exception:
        return ""


def get_module_from_path(path: str, project_root: Path) -> str:
    """Détermine le module à partir du chemin."""
    rel_path = Path(path)
    parts = rel_path.parts

    # Le module est généralement le premier ou deuxième répertoire
    if len(parts) >= 2:
        if parts[0] in ("src", "lib", "app", "pkg"):
            return parts[1] if len(parts) > 1 else parts[0]
        return parts[0]
    return "root"


def step_3_scan_files(
    config: BootstrapConfig,
    logger: logging.Logger,
    stats: BootstrapStats
) -> list[dict[str, Any]]:
    """Étape 3 : Scanner les fichiers du projet."""
    print(f"\n{Colors.BOLD}Step 3/9:{Colors.RESET} Scanning files...")

    # Collecter toutes les extensions valides
    valid_extensions = set()
    for exts in config.extensions.values():
        valid_extensions.update(exts)

    # Scanner les fichiers
    files_to_index: list[dict[str, Any]] = []
    all_files = list(config.project_root.rglob("*"))

    progress = ProgressBar(len(all_files), "Scanning")

    for file_path in all_files:
        progress.update()

        if not file_path.is_file():
            continue

        # Chemin relatif
        try:
            rel_path = file_path.relative_to(config.project_root)
        except ValueError:
            continue

        rel_path_str = str(rel_path).replace("\\", "/")

        # Vérifier les exclusions
        if should_exclude(rel_path_str, config.exclude_patterns):
            stats.files_skipped += 1
            continue

        # Vérifier l'extension
        ext = file_path.suffix.lower()
        if ext not in valid_extensions:
            stats.files_skipped += 1
            continue

        # Récupérer les infos du fichier
        language = get_language(ext, config.extensions)
        line_counts = count_lines(file_path)
        content_hash = get_content_hash(file_path)
        module = get_module_from_path(rel_path_str, config.project_root)

        file_info = {
            "path": rel_path_str,
            "filename": file_path.name,
            "extension": ext,
            "module": module,
            "language": language,
            "lines_total": line_counts["total"],
            "lines_code": line_counts["code"],
            "lines_comment": line_counts["comment"],
            "lines_blank": line_counts["blank"],
            "content_hash": content_hash,
            "full_path": file_path,
        }

        files_to_index.append(file_info)
        stats.files_scanned += 1

        logger.debug(f"Scanned: {rel_path_str}")

    progress.finish()

    # Insérer dans la base
    if files_to_index:
        conn = sqlite3.connect(str(config.db_path))
        cursor = conn.cursor()

        for f in files_to_index:
            cursor.execute("""
                INSERT INTO files (
                    path, filename, extension, module, language,
                    lines_total, lines_code, lines_comment, lines_blank,
                    content_hash, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                f["path"], f["filename"], f["extension"], f["module"], f["language"],
                f["lines_total"], f["lines_code"], f["lines_comment"], f["lines_blank"],
                f["content_hash"],
            ))
            f["id"] = cursor.lastrowid

        conn.commit()
        conn.close()

    print(f"  {Colors.GREEN}✓{Colors.RESET} Scanned {stats.files_scanned} files ({stats.files_skipped} skipped)")
    return files_to_index


# =============================================================================
# STEP 4: INDEX SYMBOLS AND RELATIONS
# =============================================================================

def run_ctags(file_path: Path) -> list[dict[str, Any]]:
    """Exécute ctags sur un fichier et retourne les symboles."""
    try:
        result = subprocess.run(
            [
                "ctags", "--output-format=json", "--fields=*",
                "-o", "-", str(file_path)
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        symbols = []
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    tag = json.loads(line)
                    symbols.append({
                        "name": tag.get("name", ""),
                        "kind": tag.get("kind", "unknown"),
                        "line_start": tag.get("line", 0),
                        "signature": tag.get("signature", ""),
                        "scope": tag.get("scope", ""),
                        "scopeKind": tag.get("scopeKind", ""),
                    })
                except json.JSONDecodeError:
                    pass

        return symbols
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def parse_python_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse un fichier Python avec ast."""
    import ast

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)

        symbols = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Construire la signature
                args = []
                for arg in node.args.args:
                    arg_str = arg.arg
                    if arg.annotation:
                        arg_str += f": {ast.unparse(arg.annotation)}"
                    args.append(arg_str)

                signature = f"({', '.join(args)})"
                if node.returns:
                    signature += f" -> {ast.unparse(node.returns)}"

                symbols.append({
                    "name": node.name,
                    "kind": "function",
                    "line_start": node.lineno,
                    "line_end": node.end_lineno,
                    "signature": signature,
                    "doc_comment": ast.get_docstring(node),
                })

            elif isinstance(node, ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases]
                symbols.append({
                    "name": node.name,
                    "kind": "class",
                    "line_start": node.lineno,
                    "line_end": node.end_lineno,
                    "base_classes": bases,
                    "doc_comment": ast.get_docstring(node),
                })

        return symbols
    except Exception:
        return []


def extract_includes(file_path: Path, language: str) -> list[dict[str, str]]:
    """Extrait les includes/imports d'un fichier."""
    includes = []

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            line = line.strip()

            if language in ("c", "cpp"):
                # #include <...> ou #include "..."
                match = re.match(r'#include\s*[<"]([^>"]+)[>"]', line)
                if match:
                    includes.append({
                        "target": match.group(1),
                        "line": i,
                        "type": "include",
                    })

            elif language == "python":
                # import ... ou from ... import ...
                match = re.match(r'(?:from\s+(\S+)\s+)?import\s+(.+)', line)
                if match:
                    module = match.group(1) or match.group(2).split(",")[0].strip()
                    includes.append({
                        "target": module.split()[0],
                        "line": i,
                        "type": "import",
                    })
    except Exception:
        pass

    return includes


def step_4_index_symbols(
    config: BootstrapConfig,
    logger: logging.Logger,
    stats: BootstrapStats,
    files: list[dict[str, Any]]
) -> None:
    """Étape 4 : Indexer les symboles et relations."""
    print(f"\n{Colors.BOLD}Step 4/9:{Colors.RESET} Indexing symbols and relations...")

    # Vérifier si ctags est disponible
    ctags_available = shutil.which("ctags") is not None
    if not ctags_available:
        logger.warning("ctags not found, using fallback parsing")
        stats.warnings.append("ctags not found, using limited parsing")

    conn = sqlite3.connect(str(config.db_path))
    cursor = conn.cursor()

    progress = ProgressBar(len(files), "Indexing")

    # Index de tous les symboles pour les relations
    all_symbols: dict[str, int] = {}

    for file_info in files:
        progress.update()

        file_id = file_info["id"]
        file_path = file_info["full_path"]
        language = file_info.get("language", "")

        # Parser les symboles
        if language == "python":
            symbols = parse_python_file(file_path)
        elif ctags_available and language in ("c", "cpp"):
            symbols = run_ctags(file_path)
        else:
            symbols = []

        # Insérer les symboles
        for sym in symbols:
            cursor.execute("""
                INSERT INTO symbols (
                    file_id, name, kind, line_start, line_end,
                    signature, doc_comment, has_doc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_id,
                sym.get("name", ""),
                sym.get("kind", "unknown"),
                sym.get("line_start"),
                sym.get("line_end"),
                sym.get("signature", ""),
                sym.get("doc_comment", ""),
                1 if sym.get("doc_comment") else 0,
            ))

            sym_id = cursor.lastrowid
            stats.symbols_indexed += 1

            # Indexer pour les relations
            all_symbols[sym.get("name", "")] = sym_id

        # Extraire les includes/imports
        includes = extract_includes(file_path, language)
        for inc in includes:
            # Chercher le fichier cible
            target_pattern = f"%{inc['target']}%"
            cursor.execute(
                "SELECT id FROM files WHERE path LIKE ?",
                (target_pattern,)
            )
            target = cursor.fetchone()

            if target:
                cursor.execute("""
                    INSERT OR IGNORE INTO file_relations (
                        source_file_id, target_file_id, relation_type, line_number
                    ) VALUES (?, ?, 'includes', ?)
                """, (file_id, target[0], inc["line"]))
                stats.file_relations_indexed += 1

        logger.debug(f"Indexed {len(symbols)} symbols from {file_info['path']}")

    progress.finish()
    conn.commit()
    conn.close()

    stats.files_indexed = len(files)
    print(f"  {Colors.GREEN}✓{Colors.RESET} Indexed {stats.symbols_indexed} symbols, {stats.file_relations_indexed} file relations")


# =============================================================================
# STEP 5: CALCULATE METRICS
# =============================================================================

def calculate_complexity(file_path: Path, language: str) -> dict[str, Any]:
    """Calcule la complexité cyclomatique d'un fichier."""
    complexity_sum = 0
    complexity_max = 0
    function_count = 0

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")

        # Compter les mots-clés de branchement
        branch_keywords = [
            r'\bif\b', r'\belse\b', r'\belif\b', r'\bfor\b', r'\bwhile\b',
            r'\bcase\b', r'\bcatch\b', r'\b\?\s*:', r'\b&&\b', r'\b\|\|\b',
            r'\band\b', r'\bor\b',
        ]

        # Complexité par fonction (estimation)
        if language == "python":
            import ast
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        func_content = ast.unparse(node)
                        func_complexity = 1
                        for kw in branch_keywords:
                            func_complexity += len(re.findall(kw, func_content))
                        complexity_sum += func_complexity
                        complexity_max = max(complexity_max, func_complexity)
                        function_count += 1
            except Exception:
                pass
        else:
            # Estimation globale pour C/C++
            for kw in branch_keywords:
                complexity_sum += len(re.findall(kw, content))
            complexity_max = complexity_sum  # Approximation
            function_count = len(re.findall(r'\b\w+\s*\([^)]*\)\s*\{', content))

    except Exception:
        pass

    avg = round(complexity_sum / function_count, 2) if function_count > 0 else 0

    return {
        "sum": complexity_sum,
        "max": complexity_max,
        "avg": avg,
    }


def step_5_calculate_metrics(
    config: BootstrapConfig,
    logger: logging.Logger,
    stats: BootstrapStats,
    files: list[dict[str, Any]]
) -> None:
    """Étape 5 : Calculer les métriques."""
    print(f"\n{Colors.BOLD}Step 5/9:{Colors.RESET} Calculating metrics...")

    conn = sqlite3.connect(str(config.db_path))
    cursor = conn.cursor()

    progress = ProgressBar(len(files), "Metrics")

    for file_info in files:
        progress.update()

        file_id = file_info["id"]
        file_path = file_info["full_path"]
        language = file_info.get("language", "")

        complexity = calculate_complexity(file_path, language)

        # Score de documentation
        cursor.execute("""
            SELECT COUNT(*), SUM(CASE WHEN has_doc = 1 THEN 1 ELSE 0 END)
            FROM symbols WHERE file_id = ?
        """, (file_id,))
        row = cursor.fetchone()
        total_symbols = row[0] or 0
        documented = row[1] or 0
        doc_score = round((documented / total_symbols * 100) if total_symbols > 0 else 0)

        # Mettre à jour les métriques
        cursor.execute("""
            UPDATE files SET
                complexity_sum = ?,
                complexity_avg = ?,
                complexity_max = ?,
                documentation_score = ?
            WHERE id = ?
        """, (
            complexity["sum"],
            complexity["avg"],
            complexity["max"],
            doc_score,
            file_id,
        ))

        logger.debug(f"Metrics for {file_info['path']}: complexity={complexity['avg']}, doc={doc_score}%")

    progress.finish()
    conn.commit()
    conn.close()

    print(f"  {Colors.GREEN}✓{Colors.RESET} Calculated metrics for {len(files)} files")


# =============================================================================
# STEP 6: ANALYZE GIT ACTIVITY
# =============================================================================

def get_git_commits(file_path: str, days: int, project_root: Path) -> int:
    """Compte les commits pour un fichier dans les N derniers jours."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"--since={days} days ago", "--", file_path],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=10,
        )
        return len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
    except Exception:
        return 0


def get_git_contributors(file_path: str, project_root: Path) -> list[str]:
    """Récupère les contributeurs d'un fichier."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%an", "--", file_path],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=10,
        )
        if result.stdout.strip():
            contributors = list(set(result.stdout.strip().split("\n")))
            return contributors[:10]  # Limite à 10
        return []
    except Exception:
        return []


def get_git_last_modified(file_path: str, project_root: Path) -> Optional[str]:
    """Récupère la date de dernière modification."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", file_path],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=10,
        )
        return result.stdout.strip() if result.stdout.strip() else None
    except Exception:
        return None


def step_6_analyze_git(
    config: BootstrapConfig,
    logger: logging.Logger,
    stats: BootstrapStats,
    files: list[dict[str, Any]]
) -> None:
    """Étape 6 : Analyser l'activité Git."""
    print(f"\n{Colors.BOLD}Step 6/9:{Colors.RESET} Analyzing Git activity...")

    # Vérifier si on est dans un repo git
    if not (config.project_root / ".git").exists():
        print(f"  {Colors.YELLOW}⚠{Colors.RESET} Not a Git repository, skipping")
        stats.warnings.append("Not a Git repository")
        return

    conn = sqlite3.connect(str(config.db_path))
    cursor = conn.cursor()

    progress = ProgressBar(len(files), "Git analysis")

    for file_info in files:
        progress.update()

        file_id = file_info["id"]
        file_path = file_info["path"]

        commits_30d = get_git_commits(file_path, 30, config.project_root)
        commits_90d = get_git_commits(file_path, 90, config.project_root)
        commits_365d = get_git_commits(file_path, 365, config.project_root)
        contributors = get_git_contributors(file_path, config.project_root)
        last_modified = get_git_last_modified(file_path, config.project_root)

        cursor.execute("""
            UPDATE files SET
                commits_30d = ?,
                commits_90d = ?,
                commits_365d = ?,
                contributors_json = ?,
                last_modified = ?
            WHERE id = ?
        """, (
            commits_30d,
            commits_90d,
            commits_365d,
            json.dumps(contributors),
            last_modified,
            file_id,
        ))

        logger.debug(f"Git for {file_path}: {commits_30d}/{commits_90d}/{commits_365d} commits")

    progress.finish()
    conn.commit()
    conn.close()

    print(f"  {Colors.GREEN}✓{Colors.RESET} Analyzed Git history for {len(files)} files")


# =============================================================================
# STEP 7: MARK CRITICAL FILES
# =============================================================================

def matches_pattern(path: str, patterns: list[str]) -> bool:
    """Vérifie si un chemin correspond à un des patterns."""
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        # Support **
        if "**" in pattern:
            regex = pattern.replace("**", ".*").replace("*", "[^/]*")
            if re.match(regex, path):
                return True
    return False


def check_security_content(file_path: Path) -> bool:
    """Vérifie si le fichier contient du code sensible."""
    security_patterns = [
        r'\bpassword\b', r'\bsecret\b', r'\btoken\b', r'\bapi_key\b',
        r'\bprivate_key\b', r'\bcredential\b',
        r'\bAES\b', r'\bRSA\b', r'\bSHA256\b', r'\bMD5\b', r'\bbcrypt\b',
        r'\bencrypt\b', r'\bdecrypt\b', r'\bhash\b',
    ]

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace").lower()
        for pattern in security_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
    except Exception:
        pass

    return False


def step_7_mark_critical(
    config: BootstrapConfig,
    logger: logging.Logger,
    stats: BootstrapStats,
    files: list[dict[str, Any]]
) -> None:
    """Étape 7 : Marquer les fichiers critiques."""
    print(f"\n{Colors.BOLD}Step 7/9:{Colors.RESET} Marking critical files...")

    conn = sqlite3.connect(str(config.db_path))
    cursor = conn.cursor()

    critical_count = 0
    security_count = 0

    progress = ProgressBar(len(files), "Criticality")

    for file_info in files:
        progress.update()

        file_id = file_info["id"]
        file_path = file_info["path"]
        full_path = file_info["full_path"]

        is_critical = False
        criticality_reason = None
        security_sensitive = False

        # Vérifier les patterns critiques
        if matches_pattern(file_path, config.critical_paths):
            is_critical = True
            criticality_reason = "matches critical path pattern"
            critical_count += 1
        elif matches_pattern(file_path, config.high_importance_paths):
            is_critical = True
            criticality_reason = "matches high importance pattern"
            critical_count += 1

        # Vérifier le contenu sensible
        if check_security_content(full_path):
            security_sensitive = True
            security_count += 1
            if not is_critical:
                is_critical = True
                criticality_reason = "contains security-sensitive content"
                critical_count += 1

        if is_critical or security_sensitive:
            cursor.execute("""
                UPDATE files SET
                    is_critical = ?,
                    criticality_reason = ?,
                    security_sensitive = ?
                WHERE id = ?
            """, (
                1 if is_critical else 0,
                criticality_reason,
                1 if security_sensitive else 0,
                file_id,
            ))

            logger.debug(f"Marked {file_path} as critical={is_critical}, security={security_sensitive}")

    progress.finish()
    conn.commit()
    conn.close()

    print(f"  {Colors.GREEN}✓{Colors.RESET} Marked {critical_count} critical files, {security_count} security-sensitive")


# =============================================================================
# STEP 8: IMPORT DEFAULT PATTERNS
# =============================================================================

DEFAULT_PATTERNS = [
    {
        "name": "error_handling_malloc",
        "category": "error_handling",
        "title": "Check malloc return value",
        "description": "Always check if malloc/calloc returns NULL before using the pointer",
        "severity": "error",
        "good_example": "char *buf = malloc(size);\nif (buf == NULL) return -1;",
        "bad_example": "char *buf = malloc(size);\nstrcpy(buf, data);  // Crash if malloc failed",
    },
    {
        "name": "error_handling_fopen",
        "category": "error_handling",
        "title": "Check fopen return value",
        "description": "Always check if fopen returns NULL before using the file handle",
        "severity": "error",
        "good_example": "FILE *fp = fopen(path, \"r\");\nif (fp == NULL) return -1;",
        "bad_example": "FILE *fp = fopen(path, \"r\");\nfread(buf, 1, size, fp);",
    },
    {
        "name": "memory_safety_strncpy",
        "category": "memory_safety",
        "title": "Use strncpy instead of strcpy",
        "description": "Prefer strncpy over strcpy to prevent buffer overflows",
        "severity": "warning",
        "good_example": "strncpy(dest, src, sizeof(dest) - 1);\ndest[sizeof(dest) - 1] = '\\0';",
        "bad_example": "strcpy(dest, src);  // Buffer overflow risk",
    },
    {
        "name": "memory_safety_free",
        "category": "memory_safety",
        "title": "Free allocated memory",
        "description": "Every malloc must have a corresponding free",
        "severity": "warning",
        "good_example": "char *buf = malloc(size);\n// use buf\nfree(buf);",
        "bad_example": "char *buf = malloc(size);\n// use buf\nreturn;  // Memory leak!",
    },
    {
        "name": "naming_functions",
        "category": "naming_convention",
        "title": "Function naming convention",
        "description": "Functions should use snake_case and be prefixed with module name",
        "severity": "info",
        "good_example": "int lcd_init(void);\nint lcd_write(uint8_t *data);",
        "bad_example": "int LCDInit(void);\nint Write(uint8_t *data);",
    },
    {
        "name": "documentation_public",
        "category": "documentation",
        "title": "Document public functions",
        "description": "All public functions should have documentation comments",
        "severity": "warning",
        "good_example": "/**\n * Initialize the LCD controller.\n * @return 0 on success, -1 on error\n */\nint lcd_init(void);",
        "bad_example": "int lcd_init(void);  // No documentation",
    },
    {
        "name": "security_input_validation",
        "category": "security",
        "title": "Validate external input",
        "description": "Always validate data from external sources (user input, network, files)",
        "severity": "error",
        "good_example": "if (len > MAX_SIZE) return -1;\nif (data == NULL) return -1;",
        "bad_example": "memcpy(buf, user_data, user_len);  // No validation!",
    },
    {
        "name": "performance_loop_invariant",
        "category": "performance",
        "title": "Move invariants out of loops",
        "description": "Move calculations that don't change inside the loop to outside",
        "severity": "info",
        "good_example": "size_t len = strlen(str);\nfor (int i = 0; i < len; i++) {...}",
        "bad_example": "for (int i = 0; i < strlen(str); i++) {...}  // strlen called each iteration",
    },
]


def step_8_import_patterns(
    config: BootstrapConfig,
    logger: logging.Logger,
    stats: BootstrapStats
) -> None:
    """Étape 8 : Importer les patterns par défaut."""
    print(f"\n{Colors.BOLD}Step 8/9:{Colors.RESET} Importing default patterns...")

    conn = sqlite3.connect(str(config.db_path))
    cursor = conn.cursor()

    imported = 0

    for pattern in DEFAULT_PATTERNS:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO patterns (
                    name, category, title, description, severity,
                    good_example, bad_example, scope, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'project', 1)
            """, (
                pattern["name"],
                pattern["category"],
                pattern["title"],
                pattern["description"],
                pattern["severity"],
                pattern.get("good_example", ""),
                pattern.get("bad_example", ""),
            ))

            if cursor.rowcount > 0:
                imported += 1
                logger.debug(f"Imported pattern: {pattern['name']}")
        except sqlite3.Error as e:
            logger.warning(f"Failed to import pattern {pattern['name']}: {e}")

    conn.commit()
    conn.close()

    print(f"  {Colors.GREEN}✓{Colors.RESET} Imported {imported} default patterns")


# =============================================================================
# STEP 9: VERIFY INTEGRITY
# =============================================================================

def step_9_verify_integrity(
    config: BootstrapConfig,
    logger: logging.Logger,
    stats: BootstrapStats
) -> bool:
    """Étape 9 : Vérifier l'intégrité de la base."""
    print(f"\n{Colors.BOLD}Step 9/9:{Colors.RESET} Verifying database integrity...")

    conn = sqlite3.connect(str(config.db_path))
    cursor = conn.cursor()

    issues = []

    # 1. Intégrité SQLite
    result = cursor.execute("PRAGMA integrity_check").fetchone()
    if result[0] != "ok":
        issues.append(f"SQLite integrity check failed: {result[0]}")

    # 2. Foreign key violations
    cursor.execute("PRAGMA foreign_key_check")
    fk_errors = cursor.fetchall()
    if fk_errors:
        issues.append(f"Foreign key violations: {len(fk_errors)}")

    # 3. Orphan symbols
    cursor.execute("""
        SELECT COUNT(*) FROM symbols s
        WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.id = s.file_id)
    """)
    orphan_symbols = cursor.fetchone()[0]
    if orphan_symbols > 0:
        issues.append(f"Orphan symbols: {orphan_symbols}")

    # 4. Stats
    cursor.execute("SELECT COUNT(*) FROM files")
    file_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM symbols")
    symbol_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM relations")
    relation_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM file_relations")
    file_relation_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM patterns")
    pattern_count = cursor.fetchone()[0]

    # 5. Test performance
    start = time.time()
    cursor.execute("""
        SELECT f.path, COUNT(s.id) as sym_count
        FROM files f
        LEFT JOIN symbols s ON s.file_id = f.id
        GROUP BY f.id
        LIMIT 100
    """)
    cursor.fetchall()
    query_time = (time.time() - start) * 1000

    if query_time > 100:
        stats.warnings.append(f"Query performance warning: {query_time:.0f}ms")

    conn.close()

    # Report
    if issues:
        for issue in issues:
            print(f"  {Colors.RED}✗{Colors.RESET} {issue}")
            stats.errors.append(issue)
        return False

    print(f"  {Colors.GREEN}✓{Colors.RESET} Database integrity verified")
    print(f"    Files: {file_count}")
    print(f"    Symbols: {symbol_count}")
    print(f"    Relations: {relation_count}")
    print(f"    File Relations: {file_relation_count}")
    print(f"    Patterns: {pattern_count}")
    print(f"    Query time: {query_time:.1f}ms")

    return True


# =============================================================================
# MAIN
# =============================================================================

def print_report(stats: BootstrapStats, success: bool) -> None:
    """Affiche le rapport final."""
    print(f"\n{'=' * 60}")

    if success:
        print(f"{Colors.GREEN}{Colors.BOLD}BOOTSTRAP COMPLETED SUCCESSFULLY{Colors.RESET}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}BOOTSTRAP COMPLETED WITH ERRORS{Colors.RESET}")

    print(f"{'=' * 60}")
    print(f"\n{Colors.BOLD}Summary:{Colors.RESET}")
    print(f"  Files scanned:    {stats.files_scanned}")
    print(f"  Files indexed:    {stats.files_indexed}")
    print(f"  Files skipped:    {stats.files_skipped}")
    print(f"  Symbols indexed:  {stats.symbols_indexed}")
    print(f"  Relations:        {stats.relations_indexed + stats.file_relations_indexed}")
    print(f"  Duration:         {stats.duration_seconds:.1f}s")

    if stats.warnings:
        print(f"\n{Colors.YELLOW}Warnings ({len(stats.warnings)}):{Colors.RESET}")
        for w in stats.warnings[:5]:
            print(f"  - {w}")
        if len(stats.warnings) > 5:
            print(f"  ... and {len(stats.warnings) - 5} more")

    if stats.errors:
        print(f"\n{Colors.RED}Errors ({len(stats.errors)}):{Colors.RESET}")
        for e in stats.errors[:5]:
            print(f"  - {e}")
        if len(stats.errors) > 5:
            print(f"  ... and {len(stats.errors) - 5} more")

    print()


def main() -> int:
    """Point d'entrée principal."""
    parser = argparse.ArgumentParser(
        description="AgentDB Bootstrap - Initialize the agent database"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Root directory of the project (default: current directory)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    # Configuration
    config = BootstrapConfig.from_project_root(args.project_root.resolve())
    stats = BootstrapStats()
    stats.start_time = time.time()

    # Setup logging
    logger = setup_logging(config.logs_dir)

    # Banner
    print(f"\n{Colors.BOLD}{Colors.CYAN}AgentDB Bootstrap{Colors.RESET}")
    print(f"{'=' * 60}")
    print(f"Project root: {config.project_root}")
    print(f"Database: {config.db_path}")

    success = True

    try:
        # Step 1: Create structure
        if not step_1_create_structure(config, logger):
            success = False

        # Step 2: Initialize schema
        if success and not step_2_init_schema(config, logger):
            success = False

        # Step 3: Scan files
        files = []
        if success:
            files = step_3_scan_files(config, logger, stats)

        # Step 4: Index symbols
        if success and files:
            step_4_index_symbols(config, logger, stats, files)

        # Step 5: Calculate metrics
        if success and files:
            step_5_calculate_metrics(config, logger, stats, files)

        # Step 6: Analyze Git
        if success and files:
            step_6_analyze_git(config, logger, stats, files)

        # Step 7: Mark critical files
        if success and files:
            step_7_mark_critical(config, logger, stats, files)

        # Step 8: Import patterns
        if success:
            step_8_import_patterns(config, logger, stats)

        # Step 9: Verify integrity
        if success:
            if not step_9_verify_integrity(config, logger, stats):
                success = False

    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Bootstrap interrupted by user{Colors.RESET}")
        success = False
    except Exception as e:
        logger.exception("Bootstrap failed")
        print(f"\n{Colors.RED}Bootstrap failed: {e}{Colors.RESET}")
        stats.errors.append(str(e))
        success = False

    stats.end_time = time.time()

    # Final report
    print_report(stats, success)

    # Update meta
    if success:
        try:
            conn = sqlite3.connect(str(config.db_path))
            conn.execute(
                "UPDATE agentdb_meta SET value = ? WHERE key = 'project_name'",
                (config.project_root.name,)
            )
            conn.execute(
                "INSERT OR REPLACE INTO agentdb_meta (key, value) VALUES ('last_bootstrap', datetime('now'))"
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    logger.info(f"Bootstrap {'completed' if success else 'failed'} in {stats.duration_seconds:.1f}s")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
