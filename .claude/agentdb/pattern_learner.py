"""
AgentDB Pattern Learner - Apprentissage automatique de patterns.

Ce module analyse l'historique des erreurs, corrections et code pour
apprendre automatiquement des patterns récurrents.

Fonctionnalités:
- Apprentissage à partir de l'historique Git (fixes)
- Détection de code smells basée sur les métriques
- Patterns basés sur l'analyse AST
- Système de feedback pour améliorer la précision

Types de patterns détectés:
- error_prone: Code susceptible de causer des bugs
- performance: Problèmes de performance
- security: Vulnérabilités potentielles
- style: Violations de conventions

Usage:
    from pattern_learner import PatternLearner

    learner = PatternLearner(db)

    # Apprendre des fixes Git
    learner.learn_from_git_history(days=90)

    # Détecter les code smells
    smells = learner.detect_code_smells("src/main.py")

    # Obtenir des suggestions
    suggestions = learner.get_suggestions("src/api.py")
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Protocol

logger = logging.getLogger("agentdb.pattern_learner")

# =============================================================================
# CONFIGURATION
# =============================================================================

# Seuils pour la détection de code smells
SMELL_THRESHOLDS = {
    "long_method": {
        "lines": 50,           # Lignes de code
        "complexity": 15,      # Complexité cyclomatique
    },
    "god_class": {
        "methods": 20,         # Nombre de méthodes
        "lines": 500,          # Lignes totales
        "dependencies": 10,    # Dépendances externes
    },
    "large_file": {
        "lines": 1000,
    },
    "high_complexity": {
        "complexity": 20,
    },
    "deep_nesting": {
        "depth": 5,
    },
    "too_many_parameters": {
        "params": 6,
    },
    "duplicate_code": {
        "min_lines": 10,
        "similarity": 0.8,
    },
}

# Patterns de commit qui indiquent un fix
FIX_COMMIT_PATTERNS = [
    r"fix(?:ed|es|ing)?[\s:]+",
    r"bug(?:fix)?[\s:]+",
    r"resolve[sd]?[\s:]+",
    r"correct(?:ed|s|ing)?[\s:]+",
    r"patch(?:ed|es)?[\s:]+",
    r"hotfix[\s:]+",
    r"repair(?:ed|s)?[\s:]+",
]

# Types d'erreurs courants à détecter
ERROR_TYPE_PATTERNS = {
    "null_pointer": [
        r"NullPointerException",
        r"None.*attribute",
        r"null reference",
        r"AttributeError.*None",
    ],
    "index_out_of_bounds": [
        r"IndexError",
        r"ArrayIndexOutOfBounds",
        r"index out of range",
    ],
    "type_error": [
        r"TypeError",
        r"type mismatch",
        r"cannot.*convert",
    ],
    "memory_leak": [
        r"memory leak",
        r"resource.*not.*closed",
        r"connection.*leak",
    ],
    "security": [
        r"injection",
        r"XSS",
        r"CSRF",
        r"vulnerability",
        r"unsafe",
    ],
    "performance": [
        r"slow",
        r"timeout",
        r"performance",
        r"optimize",
        r"bottleneck",
    ],
}


# =============================================================================
# PROTOCOLES ET TYPES
# =============================================================================

class DatabaseProtocol(Protocol):
    """Protocole pour la connexion à la base de données."""

    def execute(self, query: str, params: tuple = ()) -> Any:
        ...

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        ...

    def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        ...


@dataclass
class LearnedPattern:
    """Pattern appris automatiquement."""
    id: Optional[int] = None
    pattern_hash: str = ""
    name: str = ""
    category: str = ""  # error_prone, performance, security, style
    description: str = ""
    detection_rule: str = ""
    detection_type: str = "heuristic"
    language: Optional[str] = None
    file_pattern: Optional[str] = None
    symbol_kind: Optional[str] = None
    occurrence_count: int = 0
    fix_count: int = 0
    confidence_score: float = 0.5
    example_bad: str = ""
    example_good: str = ""
    source: str = "auto"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pattern_hash": self.pattern_hash,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "detection_rule": self.detection_rule,
            "confidence_score": self.confidence_score,
            "occurrence_count": self.occurrence_count,
            "fix_count": self.fix_count,
            "example_bad": self.example_bad,
            "example_good": self.example_good,
        }


@dataclass
class CodeSmell:
    """Code smell détecté."""
    file_path: str
    smell_type: str
    severity: str = "medium"
    confidence: float = 0.7
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    symbol_name: Optional[str] = None
    description: str = ""
    suggestion: str = ""
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "smell_type": self.smell_type,
            "severity": self.severity,
            "confidence": self.confidence,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "symbol_name": self.symbol_name,
            "description": self.description,
            "suggestion": self.suggestion,
            "metrics": self.metrics,
        }


@dataclass
class FixRecord:
    """Enregistrement d'une correction."""
    error_type: str
    error_file: str
    code_before: str
    code_after: str
    commit_hash: str = ""
    commit_message: str = ""
    commit_author: str = ""
    commit_date: str = ""
    error_line: Optional[int] = None
    fix_type: str = "bugfix"

    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type,
            "error_file": self.error_file,
            "code_before": self.code_before,
            "code_after": self.code_after,
            "commit_hash": self.commit_hash,
            "commit_message": self.commit_message,
            "fix_type": self.fix_type,
        }


# =============================================================================
# PATTERN LEARNER
# =============================================================================

class PatternLearner:
    """
    Système d'apprentissage automatique de patterns.

    Analyse l'historique du projet pour apprendre des patterns
    récurrents et suggérer des améliorations.
    """

    def __init__(self, db: DatabaseProtocol, project_root: Optional[Path] = None):
        self.db = db
        self.project_root = project_root or Path.cwd()

    # =========================================================================
    # APPRENTISSAGE DEPUIS GIT
    # =========================================================================

    def learn_from_git_history(
        self,
        days: int = 90,
        min_fixes: int = 2,
    ) -> dict[str, Any]:
        """
        Apprend des patterns à partir de l'historique Git.

        Analyse les commits de type "fix" pour identifier des patterns
        d'erreurs récurrentes et les corrections associées.

        Args:
            days: Nombre de jours d'historique à analyser
            min_fixes: Nombre minimum de fixes pour créer un pattern

        Returns:
            Statistiques d'apprentissage
        """
        stats = {
            "commits_analyzed": 0,
            "fixes_found": 0,
            "patterns_learned": 0,
            "patterns_updated": 0,
        }

        # Récupérer les commits de fix
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            result = subprocess.run(
                [
                    "git", "log",
                    f"--since={since_date}",
                    "--pretty=format:%H|%an|%ad|%s",
                    "--date=short",
                ],
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )

            if result.returncode != 0:
                logger.error(f"Git log failed: {result.stderr}")
                return stats

            commits = result.stdout.strip().split("\n")
            stats["commits_analyzed"] = len(commits)

        except Exception as e:
            logger.error(f"Failed to get git history: {e}")
            return stats

        # Analyser chaque commit
        fix_patterns = {}  # error_type -> list[FixRecord]

        for commit_line in commits:
            if not commit_line:
                continue

            parts = commit_line.split("|", 3)
            if len(parts) < 4:
                continue

            commit_hash, author, date, message = parts

            # Vérifier si c'est un commit de fix
            if not self._is_fix_commit(message):
                continue

            # Analyser le diff du commit
            fixes = self._analyze_fix_commit(commit_hash, message, author, date)

            for fix in fixes:
                stats["fixes_found"] += 1

                if fix.error_type not in fix_patterns:
                    fix_patterns[fix.error_type] = []
                fix_patterns[fix.error_type].append(fix)

                # Enregistrer le fix
                self._record_fix(fix)

        # Créer/mettre à jour les patterns
        for error_type, fixes in fix_patterns.items():
            if len(fixes) >= min_fixes:
                pattern = self._create_pattern_from_fixes(error_type, fixes)
                if self._save_pattern(pattern):
                    stats["patterns_learned"] += 1
                else:
                    stats["patterns_updated"] += 1

        logger.info(
            f"Learning complete: {stats['fixes_found']} fixes analyzed, "
            f"{stats['patterns_learned']} patterns learned"
        )

        return stats

    def _is_fix_commit(self, message: str) -> bool:
        """Vérifie si un message de commit indique un fix."""
        message_lower = message.lower()
        for pattern in FIX_COMMIT_PATTERNS:
            if re.search(pattern, message_lower):
                return True
        return False

    def _analyze_fix_commit(
        self,
        commit_hash: str,
        message: str,
        author: str,
        date: str,
    ) -> list[FixRecord]:
        """Analyse un commit de fix pour extraire les corrections."""
        fixes = []

        try:
            # Obtenir le diff
            result = subprocess.run(
                ["git", "show", "--format=", "--unified=3", commit_hash],
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )

            if result.returncode != 0:
                return fixes

            diff = result.stdout

            # Parser le diff
            current_file = None
            old_lines = []
            new_lines = []

            for line in diff.split("\n"):
                if line.startswith("diff --git"):
                    # Sauvegarder le fichier précédent
                    if current_file and (old_lines or new_lines):
                        fix = self._create_fix_record(
                            current_file, old_lines, new_lines,
                            commit_hash, message, author, date
                        )
                        if fix:
                            fixes.append(fix)

                    # Nouveau fichier
                    match = re.search(r"b/(.+)$", line)
                    current_file = match.group(1) if match else None
                    old_lines = []
                    new_lines = []

                elif line.startswith("-") and not line.startswith("---"):
                    old_lines.append(line[1:])
                elif line.startswith("+") and not line.startswith("+++"):
                    new_lines.append(line[1:])

            # Dernier fichier
            if current_file and (old_lines or new_lines):
                fix = self._create_fix_record(
                    current_file, old_lines, new_lines,
                    commit_hash, message, author, date
                )
                if fix:
                    fixes.append(fix)

        except Exception as e:
            logger.debug(f"Failed to analyze commit {commit_hash}: {e}")

        return fixes

    def _create_fix_record(
        self,
        file_path: str,
        old_lines: list[str],
        new_lines: list[str],
        commit_hash: str,
        message: str,
        author: str,
        date: str,
    ) -> Optional[FixRecord]:
        """Crée un enregistrement de fix à partir du diff."""
        if not old_lines and not new_lines:
            return None

        # Déterminer le type d'erreur
        error_type = self._classify_error_type(message, old_lines, new_lines)

        # Déterminer le type de fix
        fix_type = self._classify_fix_type(message, old_lines, new_lines)

        return FixRecord(
            error_type=error_type,
            error_file=file_path,
            code_before="\n".join(old_lines),
            code_after="\n".join(new_lines),
            commit_hash=commit_hash,
            commit_message=message,
            commit_author=author,
            commit_date=date,
            fix_type=fix_type,
        )

    def _classify_error_type(
        self,
        message: str,
        old_lines: list[str],
        new_lines: list[str],
    ) -> str:
        """Classifie le type d'erreur basé sur le message et le code."""
        combined_text = f"{message} {' '.join(old_lines)} {' '.join(new_lines)}".lower()

        for error_type, patterns in ERROR_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    return error_type

        return "general"

    def _classify_fix_type(
        self,
        message: str,
        old_lines: list[str],
        new_lines: list[str],
    ) -> str:
        """Classifie le type de correction."""
        message_lower = message.lower()

        if any(word in message_lower for word in ["security", "vuln", "inject", "xss"]):
            return "security"
        elif any(word in message_lower for word in ["perf", "optim", "slow", "fast"]):
            return "performance"
        elif any(word in message_lower for word in ["refactor", "clean", "reorgan"]):
            return "refactor"
        elif any(word in message_lower for word in ["typo", "spell", "naming"]):
            return "style"

        return "bugfix"

    def _record_fix(self, fix: FixRecord) -> None:
        """Enregistre un fix dans la base de données."""
        fix_hash = hashlib.md5(
            f"{fix.commit_hash}{fix.error_file}{fix.code_before}".encode()
        ).hexdigest()

        try:
            self.db.execute(
                """
                INSERT OR IGNORE INTO fix_history
                (fix_hash, error_type, error_file, code_before, code_after,
                 commit_hash, commit_message, commit_author, commit_date, fix_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fix_hash,
                    fix.error_type,
                    fix.error_file,
                    fix.code_before,
                    fix.code_after,
                    fix.commit_hash,
                    fix.commit_message,
                    fix.commit_author,
                    fix.commit_date,
                    fix.fix_type,
                ),
            )
        except Exception as e:
            logger.debug(f"Failed to record fix: {e}")

    def _create_pattern_from_fixes(
        self,
        error_type: str,
        fixes: list[FixRecord],
    ) -> LearnedPattern:
        """Crée un pattern à partir d'une liste de fixes similaires."""
        # Trouver les points communs dans les fixes
        files = [f.error_file for f in fixes]
        extensions = list(set(Path(f).suffix for f in files))

        # Calculer la confiance basée sur le nombre de fixes
        confidence = min(0.5 + (len(fixes) * 0.1), 0.95)

        # Générer un exemple
        example_fix = fixes[0]

        pattern = LearnedPattern(
            pattern_hash=hashlib.md5(
                f"{error_type}:{':'.join(sorted(extensions))}".encode()
            ).hexdigest(),
            name=f"auto_{error_type}",
            category=self._get_category_for_error_type(error_type),
            description=f"Pattern appris automatiquement: {error_type} (basé sur {len(fixes)} fixes)",
            detection_type="heuristic",
            language=self._detect_language_from_extensions(extensions),
            occurrence_count=len(fixes),
            fix_count=len(fixes),
            confidence_score=confidence,
            example_bad=example_fix.code_before[:500],
            example_good=example_fix.code_after[:500],
            source="auto",
        )

        return pattern

    def _get_category_for_error_type(self, error_type: str) -> str:
        """Détermine la catégorie d'un type d'erreur."""
        if error_type in ("security", "injection"):
            return "security"
        elif error_type in ("memory_leak", "performance"):
            return "performance"
        elif error_type in ("style", "naming"):
            return "style"
        return "error_prone"

    def _detect_language_from_extensions(self, extensions: list[str]) -> Optional[str]:
        """Détecte le langage à partir des extensions."""
        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
        }

        for ext in extensions:
            if ext in ext_to_lang:
                return ext_to_lang[ext]

        return None

    def _save_pattern(self, pattern: LearnedPattern) -> bool:
        """Sauvegarde ou met à jour un pattern. Retourne True si nouveau."""
        try:
            # Vérifier si le pattern existe
            existing = self.db.fetch_one(
                "SELECT id, occurrence_count FROM learned_patterns WHERE pattern_hash = ?",
                (pattern.pattern_hash,),
            )

            if existing:
                # Mettre à jour
                self.db.execute(
                    """
                    UPDATE learned_patterns
                    SET occurrence_count = occurrence_count + ?,
                        fix_count = fix_count + ?,
                        confidence_score = ?,
                        updated_at = datetime('now'),
                        last_detected_at = datetime('now')
                    WHERE pattern_hash = ?
                    """,
                    (
                        pattern.occurrence_count,
                        pattern.fix_count,
                        pattern.confidence_score,
                        pattern.pattern_hash,
                    ),
                )
                return False
            else:
                # Créer nouveau
                self.db.execute(
                    """
                    INSERT INTO learned_patterns
                    (pattern_hash, name, category, description, detection_rule,
                     detection_type, language, occurrence_count, fix_count,
                     confidence_score, example_bad, example_good, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pattern.pattern_hash,
                        pattern.name,
                        pattern.category,
                        pattern.description,
                        pattern.detection_rule,
                        pattern.detection_type,
                        pattern.language,
                        pattern.occurrence_count,
                        pattern.fix_count,
                        pattern.confidence_score,
                        pattern.example_bad,
                        pattern.example_good,
                        pattern.source,
                    ),
                )
                return True

        except Exception as e:
            logger.error(f"Failed to save pattern: {e}")
            return False

    # =========================================================================
    # DÉTECTION DE CODE SMELLS
    # =========================================================================

    def detect_code_smells(
        self,
        file_path: Optional[str] = None,
        save_to_db: bool = True,
    ) -> list[CodeSmell]:
        """
        Détecte les code smells dans un fichier ou tous les fichiers.

        Args:
            file_path: Chemin du fichier (None = tous les fichiers indexés)
            save_to_db: Sauvegarder les résultats dans la base

        Returns:
            Liste des code smells détectés
        """
        smells = []

        # Récupérer les fichiers à analyser
        if file_path:
            files = self.db.fetch_all(
                "SELECT id, path, lines_code, complexity_avg FROM files WHERE path LIKE ?",
                (f"%{file_path}%",),
            )
        else:
            files = self.db.fetch_all(
                "SELECT id, path, lines_code, complexity_avg FROM files WHERE file_type = 'source'"
            )

        for file_info in files:
            file_smells = self._detect_smells_in_file(file_info)
            smells.extend(file_smells)

            if save_to_db:
                for smell in file_smells:
                    self._save_smell(smell, file_info.get("id"))

        return smells

    def _detect_smells_in_file(self, file_info: dict) -> list[CodeSmell]:
        """Détecte les code smells dans un fichier."""
        smells = []
        file_path = file_info.get("path", "")
        file_id = file_info.get("id")

        # 1. Large file
        lines = file_info.get("lines_code", 0) or 0
        if lines > SMELL_THRESHOLDS["large_file"]["lines"]:
            smells.append(CodeSmell(
                file_path=file_path,
                smell_type="large_file",
                severity="medium",
                confidence=0.9,
                description=f"Fichier trop long ({lines} lignes)",
                suggestion="Considérez de diviser ce fichier en modules plus petits",
                metrics={"lines": lines},
            ))

        # 2. Récupérer les symboles pour analyse
        symbols = self.db.fetch_all(
            """
            SELECT id, name, kind, line_start, line_end, complexity, lines_of_code
            FROM symbols WHERE file_id = ?
            """,
            (file_id,),
        ) if file_id else []

        for sym in symbols:
            sym_smells = self._detect_symbol_smells(sym, file_path)
            smells.extend(sym_smells)

        return smells

    def _detect_symbol_smells(self, symbol: dict, file_path: str) -> list[CodeSmell]:
        """Détecte les code smells dans un symbole."""
        smells = []
        name = symbol.get("name", "")
        kind = symbol.get("kind", "")
        complexity = symbol.get("complexity", 0) or 0
        lines = symbol.get("lines_of_code", 0) or 0
        line_start = symbol.get("line_start")
        line_end = symbol.get("line_end")

        # Long method
        if kind in ("function", "method"):
            thresholds = SMELL_THRESHOLDS["long_method"]

            if lines > thresholds["lines"]:
                smells.append(CodeSmell(
                    file_path=file_path,
                    smell_type="long_method",
                    severity="medium",
                    confidence=0.85,
                    line_start=line_start,
                    line_end=line_end,
                    symbol_name=name,
                    description=f"Méthode trop longue: {name} ({lines} lignes)",
                    suggestion="Divisez cette méthode en sous-méthodes plus petites",
                    metrics={"lines": lines},
                ))

            if complexity > thresholds["complexity"]:
                severity = "high" if complexity > 25 else "medium"
                smells.append(CodeSmell(
                    file_path=file_path,
                    smell_type="high_complexity",
                    severity=severity,
                    confidence=0.9,
                    line_start=line_start,
                    line_end=line_end,
                    symbol_name=name,
                    description=f"Complexité élevée: {name} (CC={complexity})",
                    suggestion="Simplifiez la logique conditionnelle ou extrayez des sous-fonctions",
                    metrics={"complexity": complexity},
                ))

        # God class
        if kind == "class":
            # Compter les méthodes
            method_count = self.db.fetch_one(
                """
                SELECT COUNT(*) as cnt FROM symbols
                WHERE qualified_name LIKE ? AND kind IN ('method', 'function')
                """,
                (f"{name}.%",),
            )
            methods = method_count.get("cnt", 0) if method_count else 0

            thresholds = SMELL_THRESHOLDS["god_class"]

            if methods > thresholds["methods"]:
                smells.append(CodeSmell(
                    file_path=file_path,
                    smell_type="god_class",
                    severity="high",
                    confidence=0.8,
                    line_start=line_start,
                    line_end=line_end,
                    symbol_name=name,
                    description=f"Classe trop volumineuse: {name} ({methods} méthodes)",
                    suggestion="Appliquez le principe de responsabilité unique (SRP)",
                    metrics={"methods": methods, "lines": lines},
                ))

        return smells

    def _save_smell(self, smell: CodeSmell, file_id: Optional[int]) -> None:
        """Sauvegarde un code smell dans la base."""
        try:
            # Vérifier si un smell similaire existe déjà
            existing = self.db.fetch_one(
                """
                SELECT id, occurrence_count FROM code_smells
                WHERE file_path = ? AND smell_type = ? AND symbol_name = ?
                  AND status = 'open'
                """,
                (smell.file_path, smell.smell_type, smell.symbol_name),
            )

            if existing:
                # Mettre à jour le compteur
                self.db.execute(
                    """
                    UPDATE code_smells
                    SET occurrence_count = occurrence_count + 1,
                        last_seen_at = datetime('now'),
                        confidence = ?
                    WHERE id = ?
                    """,
                    (smell.confidence, existing["id"]),
                )
            else:
                # Créer nouveau
                self.db.execute(
                    """
                    INSERT INTO code_smells
                    (file_id, file_path, symbol_name, line_start, line_end,
                     smell_type, severity, confidence, description, suggestion,
                     metrics_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        smell.file_path,
                        smell.symbol_name,
                        smell.line_start,
                        smell.line_end,
                        smell.smell_type,
                        smell.severity,
                        smell.confidence,
                        smell.description,
                        smell.suggestion,
                        json.dumps(smell.metrics),
                    ),
                )

        except Exception as e:
            logger.debug(f"Failed to save smell: {e}")

    # =========================================================================
    # SUGGESTIONS
    # =========================================================================

    def get_suggestions(
        self,
        file_path: str,
        include_patterns: bool = True,
        include_smells: bool = True,
    ) -> dict[str, Any]:
        """
        Obtient des suggestions pour améliorer un fichier.

        Args:
            file_path: Chemin du fichier
            include_patterns: Inclure les patterns appris
            include_smells: Inclure les code smells

        Returns:
            Dict avec suggestions par catégorie
        """
        suggestions = {
            "file_path": file_path,
            "patterns": [],
            "smells": [],
            "summary": {
                "total": 0,
                "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            },
        }

        # Récupérer les infos du fichier
        file_info = self.db.fetch_one(
            "SELECT id, language, module FROM files WHERE path LIKE ?",
            (f"%{file_path}%",),
        )

        if include_patterns and file_info:
            # Chercher les patterns applicables
            patterns = self.db.fetch_all(
                """
                SELECT * FROM learned_patterns
                WHERE is_active = 1
                  AND confidence_score >= 0.5
                  AND (language IS NULL OR language = ?)
                ORDER BY confidence_score DESC
                LIMIT 10
                """,
                (file_info.get("language"),),
            )

            for pattern in patterns:
                suggestions["patterns"].append({
                    "name": pattern["name"],
                    "category": pattern["category"],
                    "description": pattern["description"],
                    "confidence": pattern["confidence_score"],
                    "example_bad": pattern.get("example_bad", "")[:200],
                    "example_good": pattern.get("example_good", "")[:200],
                })

        if include_smells:
            # Récupérer les code smells existants
            smells = self.db.fetch_all(
                """
                SELECT * FROM code_smells
                WHERE file_path LIKE ? AND status = 'open'
                ORDER BY
                    CASE severity
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        ELSE 4
                    END
                """,
                (f"%{file_path}%",),
            )

            for smell in smells:
                suggestions["smells"].append({
                    "type": smell["smell_type"],
                    "severity": smell["severity"],
                    "description": smell["description"],
                    "suggestion": smell["suggestion"],
                    "line": smell.get("line_start"),
                    "symbol": smell.get("symbol_name"),
                })

                # Compter par sévérité
                sev = smell["severity"]
                if sev in suggestions["summary"]["by_severity"]:
                    suggestions["summary"]["by_severity"][sev] += 1

        suggestions["summary"]["total"] = (
            len(suggestions["patterns"]) + len(suggestions["smells"])
        )

        return suggestions

    # =========================================================================
    # FEEDBACK
    # =========================================================================

    def record_feedback(
        self,
        target_type: str,  # learned_pattern, code_smell, pattern_occurrence
        target_id: int,
        is_helpful: bool,
        is_accurate: bool,
        rating: Optional[int] = None,
        comment: Optional[str] = None,
    ) -> bool:
        """
        Enregistre le feedback utilisateur pour améliorer l'apprentissage.

        Args:
            target_type: Type de cible (learned_pattern, code_smell, etc.)
            target_id: ID de la cible
            is_helpful: Le pattern/suggestion était utile
            is_accurate: La détection était correcte
            rating: Note (1-5)
            comment: Commentaire libre

        Returns:
            True si le feedback a été enregistré
        """
        try:
            self.db.execute(
                """
                INSERT INTO learning_feedback
                (feedback_type, target_type, target_id, is_helpful, is_accurate,
                 rating, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "user_feedback",
                    target_type,
                    target_id,
                    is_helpful,
                    is_accurate,
                    rating,
                    comment,
                ),
            )

            # Ajuster la confiance du pattern si négatif
            if target_type == "learned_pattern" and not is_accurate:
                self.db.execute(
                    """
                    UPDATE learned_patterns
                    SET false_positive_count = false_positive_count + 1,
                        confidence_score = MAX(0.1, confidence_score - 0.05)
                    WHERE id = ?
                    """,
                    (target_id,),
                )

            return True

        except Exception as e:
            logger.error(f"Failed to record feedback: {e}")
            return False

    # =========================================================================
    # STATISTIQUES
    # =========================================================================

    def get_learning_stats(self) -> dict[str, Any]:
        """Retourne les statistiques d'apprentissage."""
        stats = {
            "patterns": {},
            "smells": {},
            "fixes": {},
            "effectiveness": {},
        }

        # Patterns
        pattern_stats = self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
                AVG(confidence_score) as avg_confidence,
                SUM(occurrence_count) as total_occurrences
            FROM learned_patterns
            """
        )
        if pattern_stats:
            stats["patterns"] = dict(pattern_stats)

        # Smells
        smell_stats = self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open,
                SUM(CASE WHEN status = 'fixed' THEN 1 ELSE 0 END) as fixed
            FROM code_smells
            """
        )
        if smell_stats:
            stats["smells"] = dict(smell_stats)

        # Fixes
        fix_stats = self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT error_type) as error_types,
                COUNT(DISTINCT error_file) as files_affected
            FROM fix_history
            """
        )
        if fix_stats:
            stats["fixes"] = dict(fix_stats)

        # Effectiveness
        effectiveness = self.db.fetch_all("SELECT * FROM v_learning_effectiveness")
        if effectiveness:
            stats["effectiveness"] = {row["category"]: dict(row) for row in effectiveness}

        return stats


# =============================================================================
# API PUBLIQUE
# =============================================================================

def create_pattern_learner(db: DatabaseProtocol, project_root: Optional[Path] = None) -> PatternLearner:
    """Crée une instance de PatternLearner."""
    return PatternLearner(db, project_root)


__all__ = [
    # Classes
    "PatternLearner",
    "LearnedPattern",
    "CodeSmell",
    "FixRecord",
    # Factory
    "create_pattern_learner",
    # Constants
    "SMELL_THRESHOLDS",
]
