"""
AgentDB Tree-sitter Parser - Support multi-langage.

Ce module utilise tree-sitter pour parser du code dans plusieurs langages
et extraire les symboles (fonctions, classes, etc.) de manière uniforme.

Langages supportés:
- Python
- JavaScript / TypeScript
- Go
- Rust
- C / C++
- Java
- Ruby
- PHP

Installation:
    pip install tree-sitter tree-sitter-languages

Usage:
    from tree_sitter_parser import TreeSitterParser, parse_file

    # Parser un fichier
    symbols = parse_file("src/main.py")

    # Ou utiliser le parser directement
    parser = TreeSitterParser()
    symbols = parser.parse_file("src/main.go")
    relations = parser.extract_relations("src/main.go")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("agentdb.tree_sitter")

# =============================================================================
# CONFIGURATION DES LANGAGES
# =============================================================================

# Mapping extension -> langage tree-sitter
EXTENSION_TO_LANGUAGE = {
    # Python
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    # JavaScript / TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    # Go
    ".go": "go",
    # Rust
    ".rs": "rust",
    # C / C++
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".hh": "cpp",
    # Java
    ".java": "java",
    # Ruby
    ".rb": "ruby",
    ".rake": "ruby",
    # PHP
    ".php": "php",
    # Kotlin
    ".kt": "kotlin",
    ".kts": "kotlin",
    # Swift
    ".swift": "swift",
    # Scala
    ".scala": "scala",
    # C#
    ".cs": "c_sharp",
    # Bash
    ".sh": "bash",
    ".bash": "bash",
    # SQL
    ".sql": "sql",
    # YAML
    ".yml": "yaml",
    ".yaml": "yaml",
    # JSON
    ".json": "json",
    # TOML
    ".toml": "toml",
}

# Queries tree-sitter pour extraire les symboles par langage
SYMBOL_QUERIES = {
    "python": """
        (function_definition
            name: (identifier) @func.name
            parameters: (parameters) @func.params
            return_type: (type)? @func.return_type
            body: (block) @func.body) @function

        (class_definition
            name: (identifier) @class.name
            superclasses: (argument_list)? @class.bases
            body: (block) @class.body) @class

        (decorated_definition
            (decorator) @decorator
            definition: (_) @decorated)
    """,

    "javascript": """
        (function_declaration
            name: (identifier) @func.name
            parameters: (formal_parameters) @func.params
            body: (statement_block) @func.body) @function

        (class_declaration
            name: (identifier) @class.name
            body: (class_body) @class.body) @class

        (method_definition
            name: (property_identifier) @method.name
            parameters: (formal_parameters) @method.params
            body: (statement_block) @method.body) @method

        (arrow_function
            parameters: (_) @arrow.params
            body: (_) @arrow.body) @arrow_function

        (variable_declarator
            name: (identifier) @var.name
            value: (arrow_function)) @arrow_var
    """,

    "typescript": """
        (function_declaration
            name: (identifier) @func.name
            parameters: (formal_parameters) @func.params
            return_type: (type_annotation)? @func.return_type
            body: (statement_block) @func.body) @function

        (class_declaration
            name: (type_identifier) @class.name
            body: (class_body) @class.body) @class

        (interface_declaration
            name: (type_identifier) @interface.name
            body: (interface_body) @interface.body) @interface

        (type_alias_declaration
            name: (type_identifier) @type.name
            value: (_) @type.value) @type_alias

        (method_definition
            name: (property_identifier) @method.name
            parameters: (formal_parameters) @method.params
            body: (statement_block) @method.body) @method
    """,

    "go": """
        (function_declaration
            name: (identifier) @func.name
            parameters: (parameter_list) @func.params
            result: (_)? @func.return_type
            body: (block) @func.body) @function

        (method_declaration
            receiver: (parameter_list) @method.receiver
            name: (field_identifier) @method.name
            parameters: (parameter_list) @method.params
            result: (_)? @method.return_type
            body: (block) @method.body) @method

        (type_declaration
            (type_spec
                name: (type_identifier) @type.name
                type: (_) @type.def)) @type_decl

        (struct_type
            (field_declaration_list) @struct.fields) @struct
    """,

    "rust": """
        (function_item
            name: (identifier) @func.name
            parameters: (parameters) @func.params
            return_type: (_)? @func.return_type
            body: (block) @func.body) @function

        (impl_item
            trait: (_)? @impl.trait
            type: (_) @impl.type
            body: (declaration_list) @impl.body) @impl

        (struct_item
            name: (type_identifier) @struct.name
            body: (_)? @struct.body) @struct

        (enum_item
            name: (type_identifier) @enum.name
            body: (enum_variant_list) @enum.body) @enum

        (trait_item
            name: (type_identifier) @trait.name
            body: (declaration_list) @trait.body) @trait
    """,

    "c": """
        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @func.name
                parameters: (parameter_list) @func.params)
            body: (compound_statement) @func.body) @function

        (struct_specifier
            name: (type_identifier) @struct.name
            body: (field_declaration_list)? @struct.body) @struct

        (enum_specifier
            name: (type_identifier)? @enum.name
            body: (enumerator_list)? @enum.body) @enum

        (type_definition
            declarator: (_) @typedef.name) @typedef
    """,

    "cpp": """
        (function_definition
            declarator: (function_declarator
                declarator: (_) @func.name
                parameters: (parameter_list) @func.params)
            body: (compound_statement) @func.body) @function

        (class_specifier
            name: (type_identifier) @class.name
            body: (field_declaration_list)? @class.body) @class

        (struct_specifier
            name: (type_identifier) @struct.name
            body: (field_declaration_list)? @struct.body) @struct

        (namespace_definition
            name: (identifier)? @namespace.name
            body: (declaration_list) @namespace.body) @namespace

        (template_declaration
            (function_definition) @template_func) @template
    """,

    "java": """
        (method_declaration
            name: (identifier) @method.name
            parameters: (formal_parameters) @method.params
            body: (block) @method.body) @method

        (class_declaration
            name: (identifier) @class.name
            body: (class_body) @class.body) @class

        (interface_declaration
            name: (identifier) @interface.name
            body: (interface_body) @interface.body) @interface

        (enum_declaration
            name: (identifier) @enum.name
            body: (enum_body) @enum.body) @enum

        (constructor_declaration
            name: (identifier) @constructor.name
            parameters: (formal_parameters) @constructor.params
            body: (constructor_body) @constructor.body) @constructor
    """,
}

# Queries pour les imports/includes
IMPORT_QUERIES = {
    "python": """
        (import_statement
            name: (dotted_name) @import.name) @import

        (import_from_statement
            module_name: (dotted_name) @from.module
            name: (_) @from.names) @from_import
    """,

    "javascript": """
        (import_statement
            source: (string) @import.source) @import

        (import_clause
            (identifier) @import.default
            (named_imports)? @import.named) @import_clause
    """,

    "typescript": """
        (import_statement
            source: (string) @import.source) @import
    """,

    "go": """
        (import_declaration
            (import_spec
                path: (interpreted_string_literal) @import.path)) @import

        (import_declaration
            (import_spec_list
                (import_spec
                    path: (interpreted_string_literal) @import.path))) @import_list
    """,

    "rust": """
        (use_declaration
            argument: (_) @use.path) @use
    """,

    "c": """
        (preproc_include
            path: (_) @include.path) @include
    """,

    "cpp": """
        (preproc_include
            path: (_) @include.path) @include
    """,

    "java": """
        (import_declaration
            (scoped_identifier) @import.path) @import
    """,
}

# Mapping statique des types de nœuds vers les kinds (optimisation)
_TYPE_MAPPINGS = {
    # Python
    "function_definition": "function",
    "async_function_definition": "function",
    "class_definition": "class",
    # JavaScript/TypeScript
    "function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    # Go
    "method_declaration": "method",
    "type_declaration": "type",
    # Rust
    "function_item": "function",
    "struct_item": "struct",
    "enum_item": "enum",
    "trait_item": "trait",
    "impl_item": "impl",
    # C/C++
    "struct_specifier": "struct",
    "enum_specifier": "enum",
    "class_specifier": "class",
    "namespace_definition": "namespace",
    # Java
    "constructor_declaration": "constructor",
    "enum_declaration": "enum",
}

# Nœuds qui augmentent la complexité cyclomatique (optimisation)
_COMPLEXITY_NODES = frozenset({
    "if_statement", "if_expression", "elif_clause",
    "for_statement", "for_expression", "for_in_statement",
    "while_statement", "while_expression",
    "try_statement", "except_clause", "catch_clause",
    "with_statement",
    "match_statement", "match_expression", "case_clause",
    "conditional_expression", "ternary_expression",
})

# Queries pour les appels de fonctions
CALL_QUERIES = {
    "python": """
        (call
            function: (identifier) @call.name) @call

        (call
            function: (attribute
                attribute: (identifier) @call.method)) @method_call
    """,

    "javascript": """
        (call_expression
            function: (identifier) @call.name) @call

        (call_expression
            function: (member_expression
                property: (property_identifier) @call.method)) @method_call
    """,

    "go": """
        (call_expression
            function: (identifier) @call.name) @call

        (call_expression
            function: (selector_expression
                field: (field_identifier) @call.method)) @method_call
    """,

    "rust": """
        (call_expression
            function: (identifier) @call.name) @call

        (call_expression
            function: (field_expression
                field: (field_identifier) @call.method)) @method_call
    """,

    "c": """
        (call_expression
            function: (identifier) @call.name) @call
    """,

    "cpp": """
        (call_expression
            function: (identifier) @call.name) @call

        (call_expression
            function: (field_expression
                field: (field_identifier) @call.method)) @method_call
    """,

    "java": """
        (method_invocation
            name: (identifier) @call.name) @call
    """,
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ParsedSymbol:
    """Symbole extrait du code source."""
    name: str
    kind: str  # function, method, class, struct, interface, enum, type, etc.
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0
    signature: str = ""
    return_type: str = ""
    visibility: str = "public"
    is_static: bool = False
    is_async: bool = False
    is_exported: bool = False
    qualified_name: str = ""
    doc_comment: str = ""
    complexity: int = 1
    parameters: list[dict] = field(default_factory=list)
    base_classes: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    language: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire pour la DB."""
        return {
            "name": self.name,
            "kind": self.kind,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "column_start": self.column_start,
            "column_end": self.column_end,
            "signature": self.signature,
            "return_type": self.return_type,
            "visibility": self.visibility,
            "is_static": self.is_static,
            "is_exported": self.is_exported,
            "qualified_name": self.qualified_name or self.name,
            "doc_comment": self.doc_comment,
            "complexity": self.complexity,
            "parameters_json": self.parameters,
            "base_classes_json": self.base_classes,
        }


@dataclass
class ParsedImport:
    """Import/include extrait du code source."""
    module: str
    names: list[str] = field(default_factory=list)
    alias: str = ""
    line: int = 0
    is_relative: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "names": self.names,
            "alias": self.alias,
            "line": self.line,
            "is_relative": self.is_relative,
        }


@dataclass
class ParsedCall:
    """Appel de fonction extrait du code source."""
    name: str
    line: int
    column: int = 0
    is_method: bool = False
    receiver: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "line": self.line,
            "column": self.column,
            "is_method": self.is_method,
            "receiver": self.receiver,
        }


@dataclass
class ParseResult:
    """Résultat complet du parsing d'un fichier."""
    file_path: str
    language: str
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    calls: list[ParsedCall] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    parse_time_ms: float = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "symbols": [s.to_dict() for s in self.symbols],
            "imports": [i.to_dict() for i in self.imports],
            "calls": [c.to_dict() for c in self.calls],
            "errors": self.errors,
            "stats": {
                "symbol_count": len(self.symbols),
                "import_count": len(self.imports),
                "call_count": len(self.calls),
                "parse_time_ms": self.parse_time_ms,
            },
        }


# =============================================================================
# TREE-SITTER PARSER
# =============================================================================

class TreeSitterParser:
    """
    Parser multi-langage basé sur tree-sitter.

    Supporte deux modes :
    - Bindings individuels modernes (tree-sitter-python, tree-sitter-c, etc.)
    - Legacy tree-sitter-languages (pour compatibilité)
    """

    _instance: Optional["TreeSitterParser"] = None
    _available: Optional[bool] = None
    _use_individual_bindings: bool = False
    _parsers: dict = {}

    # Mapping langage -> module binding individuel
    _LANGUAGE_MODULES = {
        "python": "tree_sitter_python",
        "c": "tree_sitter_c",
        "cpp": "tree_sitter_cpp",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
        "tsx": "tree_sitter_typescript",
        "go": "tree_sitter_go",
        "rust": "tree_sitter_rust",
        "java": "tree_sitter_java",
        "ruby": "tree_sitter_ruby",
        "php": "tree_sitter_php",
    }

    def __new__(cls) -> "TreeSitterParser":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._parsers = {}
        self._languages = {}

    @classmethod
    def is_available(cls) -> bool:
        """Vérifie si tree-sitter est disponible (bindings individuels ou legacy)."""
        if cls._available is None:
            # Essayer d'abord les bindings individuels (moderne)
            try:
                from tree_sitter import Parser, Language
                import tree_sitter_python
                # Test rapide de l'API moderne
                parser = Parser()
                parser.language = Language(tree_sitter_python.language())
                cls._available = True
                cls._use_individual_bindings = True
                logger.info("tree-sitter: using individual bindings (modern)")
            except (ImportError, TypeError, AttributeError):
                # Fallback sur tree-sitter-languages (legacy)
                try:
                    import tree_sitter_languages  # noqa: F401
                    cls._available = True
                    cls._use_individual_bindings = False
                    logger.info("tree-sitter: using tree-sitter-languages (legacy)")
                except ImportError:
                    cls._available = False
                    logger.warning(
                        "tree-sitter non disponible. Installez avec: "
                        "pip install -r .claude/agentdb/requirements.txt"
                    )
        return cls._available

    def get_parser(self, language: str):
        """Retourne le parser pour un langage donné."""
        if not self.is_available():
            return None

        if language not in self._parsers:
            try:
                if self._use_individual_bindings:
                    self._load_individual_parser(language)
                else:
                    self._load_legacy_parser(language)
            except Exception as e:
                logger.warning(f"Could not load parser for {language}: {e}")
                return None

        return self._parsers.get(language)

    def _load_individual_parser(self, language: str):
        """Charge un parser via les bindings individuels modernes."""
        from tree_sitter import Parser, Language
        import importlib

        module_name = self._LANGUAGE_MODULES.get(language)
        if not module_name:
            raise ImportError(f"No binding module for language: {language}")

        # Importer dynamiquement le module de langage
        lang_module = importlib.import_module(module_name)

        # Créer le parser avec la nouvelle API
        parser = Parser()
        lang = Language(lang_module.language())
        parser.language = lang

        self._parsers[language] = parser
        self._languages[language] = lang

    def _load_legacy_parser(self, language: str):
        """Charge un parser via tree-sitter-languages (legacy)."""
        import tree_sitter_languages
        self._parsers[language] = tree_sitter_languages.get_parser(language)
        self._languages[language] = tree_sitter_languages.get_language(language)

    def get_language(self, language: str):
        """Retourne l'objet Language pour un langage donné."""
        if language not in self._languages:
            self.get_parser(language)  # Charge le langage
        return self._languages.get(language)

    def detect_language(self, file_path: Path) -> Optional[str]:
        """Détecte le langage à partir de l'extension."""
        suffix = file_path.suffix.lower()
        return EXTENSION_TO_LANGUAGE.get(suffix)

    def parse_file(self, file_path: Path | str) -> ParseResult:
        """
        Parse un fichier et extrait les symboles.

        Args:
            file_path: Chemin du fichier à parser

        Returns:
            ParseResult avec symboles, imports, et appels
        """
        import time
        start = time.time()

        file_path = Path(file_path)
        result = ParseResult(file_path=str(file_path), language="")

        # Détecter le langage
        language = self.detect_language(file_path)
        if not language:
            result.errors.append(f"Unknown language for extension: {file_path.suffix}")
            return result

        result.language = language

        # Vérifier disponibilité tree-sitter
        if not self.is_available():
            # Fallback sur les parsers natifs
            return self._fallback_parse(file_path, language)

        # Parser le fichier
        parser = self.get_parser(language)
        if not parser:
            result.errors.append(f"No parser available for {language}")
            return self._fallback_parse(file_path, language)

        try:
            content = file_path.read_bytes()
            tree = parser.parse(content)

            # OPTIMISATION: Pré-décoder le contenu et les lignes une seule fois
            content_str = content.decode("utf-8", errors="replace")
            lines = content_str.split("\n")

            # OPTIMISATION: Traversée unique de l'AST pour tout extraire
            result.symbols, result.imports, result.calls = self._extract_all(
                tree, content, language, lines
            )

        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            result.errors.append(str(e))
            # Essayer le fallback
            fallback = self._fallback_parse(file_path, language)
            if fallback.symbols:
                return fallback

        result.parse_time_ms = (time.time() - start) * 1000
        return result

    def _extract_all(
        self, tree, content: bytes, language: str, lines: list[str]
    ) -> tuple[list[ParsedSymbol], list[ParsedImport], list[ParsedCall]]:
        """
        OPTIMISATION: Extrait symboles, imports et calls en une seule traversée.

        Args:
            tree: AST tree-sitter
            content: Contenu brut en bytes
            language: Langage du fichier
            lines: Lignes pré-découpées (évite de re-split)

        Returns:
            Tuple (symbols, imports, calls)
        """
        symbols = []
        imports = []
        calls = []

        root = tree.root_node

        # Types de noeuds pour chaque catégorie
        symbol_types = {
            "function_definition", "async_function_definition", "class_definition",
            "function_declaration", "class_declaration", "method_definition",
            "interface_declaration", "type_alias_declaration",
            "method_declaration", "function_item", "struct_item", "enum_item",
            "trait_item", "impl_item", "struct_specifier", "enum_specifier",
            "class_specifier", "namespace_definition", "constructor_declaration",
        }

        import_types = {
            "import_statement", "import_from_statement", "import_declaration",
            "use_declaration", "preproc_include",
        }

        call_types = {"call_expression", "call", "method_invocation"}

        # Utiliser une pile au lieu de la récursion pour éviter stack overflow
        # et améliorer les performances
        stack = [(root, None)]  # (node, parent_class)

        while stack:
            node, parent_class = stack.pop()
            node_type = node.type

            # Extraire symbole si applicable
            if node_type in symbol_types:
                symbol = self._node_to_symbol_fast(node, content, language, parent_class, lines)
                if symbol:
                    symbols.append(symbol)
                    # Mettre à jour parent_class pour les enfants si c'est une classe
                    if symbol.kind == "class":
                        parent_class = symbol.name

            # Extraire import si applicable
            elif node_type in import_types:
                imp = self._node_to_import(node, content, language)
                if imp:
                    imports.append(imp)

            # Extraire call si applicable
            elif node_type in call_types:
                call = self._node_to_call(node, content, language)
                if call:
                    calls.append(call)

            # Ajouter les enfants à la pile (en ordre inverse pour traitement LIFO correct)
            for child in reversed(node.children):
                stack.append((child, parent_class))

        return symbols, imports, calls

    def _extract_symbols(
        self, tree, content: bytes, language: str
    ) -> list[ParsedSymbol]:
        """Extrait les symboles d'un AST tree-sitter (méthode legacy)."""
        # Utiliser la nouvelle méthode optimisée
        lines = content.decode("utf-8", errors="replace").split("\n")
        symbols, _, _ = self._extract_all(tree, content, language, lines)
        return symbols

    def _node_to_symbol(
        self, node, content: bytes, language: str, parent_class: Optional[str] = None
    ) -> Optional[ParsedSymbol]:
        """Convertit un nœud tree-sitter en ParsedSymbol."""
        node_type = node.type

        # Mapping générique des types de nœuds vers les kinds
        type_mappings = {
            # Python
            "function_definition": "function",
            "async_function_definition": "function",
            "class_definition": "class",
            # JavaScript/TypeScript
            "function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
            "interface_declaration": "interface",
            "type_alias_declaration": "type",
            # Go
            "function_declaration": "function",
            "method_declaration": "method",
            "type_declaration": "type",
            # Rust
            "function_item": "function",
            "struct_item": "struct",
            "enum_item": "enum",
            "trait_item": "trait",
            "impl_item": "impl",
            # C/C++
            "struct_specifier": "struct",
            "enum_specifier": "enum",
            "class_specifier": "class",
            "namespace_definition": "namespace",
            # Java
            "method_declaration": "method",
            "constructor_declaration": "constructor",
            "enum_declaration": "enum",
            "interface_declaration": "interface",
        }

        kind = type_mappings.get(node_type)
        if not kind:
            return None

        # Extraire le nom
        name = self._get_node_name(node, language)
        if not name:
            return None

        # Créer le symbole
        symbol = ParsedSymbol(
            name=name,
            kind=kind,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            column_start=node.start_point[1],
            column_end=node.end_point[1],
            language=language,
        )

        # Qualified name si dans une classe
        if parent_class:
            symbol.qualified_name = f"{parent_class}.{name}"
            if kind == "function":
                symbol.kind = "method"

        # Extraire la signature
        symbol.signature = self._extract_signature(node, content, language)

        # Extraire la visibilité
        symbol.visibility = self._extract_visibility(node, name, language)

        # Extraire le docstring
        symbol.doc_comment = self._extract_docstring(node, content, language)

        # Calculer la complexité
        symbol.complexity = self._calculate_complexity(node, language)

        # Vérifier async
        if "async" in node_type:
            symbol.is_async = True

        # Extraire les bases pour les classes
        if kind == "class":
            symbol.base_classes = self._extract_base_classes(node, content, language)

        return symbol

    def _node_to_symbol_fast(
        self, node, content: bytes, language: str, parent_class: Optional[str],
        lines: list[str]
    ) -> Optional[ParsedSymbol]:
        """
        Version optimisée de _node_to_symbol qui réutilise les lignes pré-découpées.
        """
        node_type = node.type

        # Mapping statique (déplacé en attribut de classe pour éviter recréation)
        kind = _TYPE_MAPPINGS.get(node_type)
        if not kind:
            return None

        # Extraire le nom
        name = self._get_node_name(node, language)
        if not name:
            return None

        # Créer le symbole avec les champs de base
        symbol = ParsedSymbol(
            name=name,
            kind=kind,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            column_start=node.start_point[1],
            column_end=node.end_point[1],
            language=language,
        )

        # Qualified name si dans une classe
        if parent_class:
            symbol.qualified_name = f"{parent_class}.{name}"
            if kind == "function":
                symbol.kind = "method"

        # Extraire la signature
        symbol.signature = self._extract_signature(node, content, language)

        # Extraire la visibilité (rapide, pas de décodage)
        symbol.visibility = self._extract_visibility(node, name, language)

        # OPTIMISATION: Extraire le docstring avec les lignes pré-découpées
        symbol.doc_comment = self._extract_docstring_fast(node, language, lines)

        # OPTIMISATION: Calculer la complexité avec itération au lieu de récursion
        symbol.complexity = self._calculate_complexity_fast(node)

        # Vérifier async
        if "async" in node_type:
            symbol.is_async = True

        # Extraire les bases pour les classes
        if kind == "class":
            symbol.base_classes = self._extract_base_classes(node, content, language)

        return symbol

    def _get_node_name(self, node, language: str) -> Optional[str]:
        """Extrait le nom d'un nœud."""
        # Chercher un enfant 'name' ou 'identifier'
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "property_identifier",
                             "field_identifier", "name"):
                return child.text.decode("utf-8")

            # Pour les déclarations de fonctions C/C++
            if child.type in ("function_declarator", "declarator"):
                return self._get_node_name(child, language)

        return None

    def _extract_signature(self, node, content: bytes, language: str) -> str:
        """Extrait la signature d'une fonction/méthode."""
        # Chercher les paramètres
        params_text = ""
        return_text = ""

        for child in node.children:
            if child.type in ("parameters", "formal_parameters", "parameter_list"):
                params_text = child.text.decode("utf-8")
            elif child.type in ("type", "type_annotation", "return_type"):
                return_text = child.text.decode("utf-8")

        signature = params_text
        if return_text:
            signature += f" -> {return_text}"

        return signature

    def _extract_visibility(self, node, name: str, language: str) -> str:
        """Extrait la visibilité d'un symbole."""
        # Python: convention _name = protected, __name = private
        if language == "python":
            if name.startswith("__") and not name.endswith("__"):
                return "private"
            elif name.startswith("_"):
                return "protected"
            return "public"

        # Go: majuscule = public
        if language == "go":
            if name and name[0].isupper():
                return "public"
            return "private"

        # Rust: pub keyword
        if language == "rust":
            node_text = node.text.decode("utf-8")
            if node_text.startswith("pub "):
                return "public"
            return "private"

        # Java/TypeScript: chercher les modifiers
        for child in node.children:
            if child.type == "modifiers":
                modifiers = child.text.decode("utf-8")
                if "private" in modifiers:
                    return "private"
                elif "protected" in modifiers:
                    return "protected"
                elif "public" in modifiers:
                    return "public"

        return "public"

    def _extract_docstring(self, node, content: bytes, language: str) -> str:
        """Extrait le docstring/commentaire de documentation."""
        # Chercher un commentaire juste avant le nœud
        start_line = node.start_point[0]
        lines = content.decode("utf-8", errors="replace").split("\n")

        doc_lines = []

        # Python: chercher une string comme premier statement
        if language == "python":
            for child in node.children:
                if child.type == "block":
                    for block_child in child.children:
                        if block_child.type == "expression_statement":
                            for expr in block_child.children:
                                if expr.type == "string":
                                    return expr.text.decode("utf-8").strip('"""\'')
                        break

        # Chercher des commentaires au-dessus
        for i in range(start_line - 1, max(start_line - 10, -1), -1):
            if i < 0 or i >= len(lines):
                continue
            line = lines[i].strip()
            if language in ("python",) and line.startswith("#"):
                doc_lines.insert(0, line[1:].strip())
            elif language in ("javascript", "typescript", "go", "rust", "c", "cpp", "java"):
                if line.startswith("//"):
                    doc_lines.insert(0, line[2:].strip())
                elif line.startswith("*"):
                    doc_lines.insert(0, line[1:].strip())
                elif line.startswith("/*") or line.endswith("*/"):
                    continue
                elif line:
                    break
            else:
                break

        return "\n".join(doc_lines)

    def _calculate_complexity(self, node, language: str) -> int:
        """Calcule la complexité cyclomatique."""
        complexity = 1

        # Nœuds qui augmentent la complexité
        complexity_nodes = {
            "if_statement", "if_expression", "elif_clause", "else_clause",
            "for_statement", "for_expression", "for_in_statement",
            "while_statement", "while_expression",
            "try_statement", "except_clause", "catch_clause",
            "with_statement",
            "match_statement", "match_expression", "case_clause",
            "conditional_expression", "ternary_expression",
            "binary_expression",  # && et ||
            "boolean_operator",
        }

        def count_complexity(n):
            nonlocal complexity
            if n.type in complexity_nodes:
                complexity += 1
            # Pour les opérateurs booléens, ajouter pour chaque opérande
            if n.type in ("binary_expression", "boolean_operator"):
                text = n.text.decode("utf-8")
                complexity += text.count("&&") + text.count("||") + text.count(" and ") + text.count(" or ")

            for child in n.children:
                count_complexity(child)

        count_complexity(node)
        return complexity

    def _extract_docstring_fast(self, node, language: str, lines: list[str]) -> str:
        """
        Version optimisée qui utilise les lignes pré-découpées.
        Évite de re-décoder et re-splitter le contenu pour chaque symbole.
        """
        start_line = node.start_point[0]
        doc_lines = []

        # Python: chercher une string comme premier statement
        if language == "python":
            for child in node.children:
                if child.type == "block":
                    for block_child in child.children:
                        if block_child.type == "expression_statement":
                            for expr in block_child.children:
                                if expr.type == "string":
                                    return expr.text.decode("utf-8").strip('"""\'')
                        break

        # Chercher des commentaires au-dessus (limité à 10 lignes)
        for i in range(start_line - 1, max(start_line - 10, -1), -1):
            if i < 0 or i >= len(lines):
                continue
            line = lines[i].strip()
            if language == "python" and line.startswith("#"):
                doc_lines.insert(0, line[1:].strip())
            elif language in ("javascript", "typescript", "go", "rust", "c", "cpp", "java"):
                if line.startswith("//"):
                    doc_lines.insert(0, line[2:].strip())
                elif line.startswith("*"):
                    doc_lines.insert(0, line[1:].strip())
                elif line.startswith("/*") or line.endswith("*/"):
                    continue
                elif line:
                    break
            else:
                break

        return "\n".join(doc_lines)

    def _calculate_complexity_fast(self, node) -> int:
        """
        Version optimisée utilisant une pile au lieu de la récursion.
        Évite aussi le décodage UTF-8 répété pour les opérateurs booléens.
        """
        complexity = 1

        # Utiliser une pile pour éviter la récursion
        stack = [node]

        while stack:
            n = stack.pop()
            node_type = n.type

            if node_type in _COMPLEXITY_NODES:
                complexity += 1

            # Pour les opérateurs booléens, compter les opérateurs sans décoder tout le texte
            if node_type in ("binary_expression", "boolean_operator"):
                # Optimisation: compter directement dans les bytes
                text = n.text
                complexity += (
                    text.count(b"&&") +
                    text.count(b"||") +
                    text.count(b" and ") +
                    text.count(b" or ")
                )

            # Ajouter les enfants à la pile
            stack.extend(n.children)

        return complexity

    def _extract_base_classes(self, node, content: bytes, language: str) -> list[str]:
        """Extrait les classes de base."""
        bases = []

        for child in node.children:
            # Python: argument_list après le nom
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "identifier":
                        bases.append(arg.text.decode("utf-8"))

            # Java/TypeScript: extends/implements
            if child.type in ("superclass", "extends_clause", "implements_clause"):
                for sub in child.children:
                    if sub.type in ("identifier", "type_identifier"):
                        bases.append(sub.text.decode("utf-8"))

        return bases

    def _extract_imports(
        self, tree, content: bytes, language: str
    ) -> list[ParsedImport]:
        """Extrait les imports d'un AST."""
        imports = []
        root = tree.root_node

        def visit(node):
            imp = self._node_to_import(node, content, language)
            if imp:
                imports.append(imp)

            for child in node.children:
                visit(child)

        visit(root)
        return imports

    def _node_to_import(
        self, node, content: bytes, language: str
    ) -> Optional[ParsedImport]:
        """Convertit un nœud en ParsedImport."""
        import_types = {
            "import_statement", "import_from_statement", "import_declaration",
            "use_declaration", "preproc_include",
        }

        if node.type not in import_types:
            return None

        imp = ParsedImport(module="", line=node.start_point[0] + 1)

        # Extraire le module selon le langage
        if language == "python":
            for child in node.children:
                if child.type == "dotted_name":
                    imp.module = child.text.decode("utf-8")
                elif child.type == "aliased_import":
                    for sub in child.children:
                        if sub.type == "dotted_name":
                            imp.module = sub.text.decode("utf-8")
                        elif sub.type == "identifier":
                            imp.alias = sub.text.decode("utf-8")

        elif language in ("javascript", "typescript"):
            for child in node.children:
                if child.type == "string":
                    imp.module = child.text.decode("utf-8").strip("'\"")

        elif language == "go":
            for child in node.children:
                if child.type == "interpreted_string_literal":
                    imp.module = child.text.decode("utf-8").strip('"')
                elif child.type == "import_spec_list":
                    for spec in child.children:
                        if spec.type == "import_spec":
                            for sub in spec.children:
                                if sub.type == "interpreted_string_literal":
                                    imports_module = sub.text.decode("utf-8").strip('"')
                                    imp.module = imports_module

        elif language == "rust":
            for child in node.children:
                if child.type in ("scoped_identifier", "identifier", "use_wildcard"):
                    imp.module = child.text.decode("utf-8")

        elif language in ("c", "cpp"):
            for child in node.children:
                if child.type in ("string_literal", "system_lib_string"):
                    imp.module = child.text.decode("utf-8").strip('<>"')

        elif language == "java":
            for child in node.children:
                if child.type == "scoped_identifier":
                    imp.module = child.text.decode("utf-8")

        return imp if imp.module else None

    def _extract_calls(
        self, tree, content: bytes, language: str
    ) -> list[ParsedCall]:
        """Extrait les appels de fonctions d'un AST."""
        calls = []
        root = tree.root_node

        def visit(node):
            call = self._node_to_call(node, content, language)
            if call:
                calls.append(call)

            for child in node.children:
                visit(child)

        visit(root)
        return calls

    def _node_to_call(
        self, node, content: bytes, language: str
    ) -> Optional[ParsedCall]:
        """Convertit un nœud en ParsedCall."""
        call_types = {"call_expression", "call", "method_invocation"}

        if node.type not in call_types:
            return None

        call = ParsedCall(
            name="",
            line=node.start_point[0] + 1,
            column=node.start_point[1],
        )

        for child in node.children:
            if child.type == "identifier":
                call.name = child.text.decode("utf-8")
            elif child.type in ("attribute", "member_expression", "selector_expression", "field_expression"):
                # Appel de méthode
                call.is_method = True
                for sub in child.children:
                    if sub.type in ("identifier", "property_identifier", "field_identifier"):
                        if not call.receiver:
                            call.receiver = sub.text.decode("utf-8")
                        else:
                            call.name = sub.text.decode("utf-8")

        return call if call.name else None

    def _fallback_parse(self, file_path: Path, language: str) -> ParseResult:
        """Fallback sur les parsers natifs si tree-sitter non disponible."""
        result = ParseResult(file_path=str(file_path), language=language)

        if language == "python":
            try:
                import ast
                content = file_path.read_text(encoding="utf-8")
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        result.symbols.append(ParsedSymbol(
                            name=node.name,
                            kind="function",
                            line_start=node.lineno,
                            line_end=node.end_lineno or node.lineno,
                            language=language,
                            is_async=isinstance(node, ast.AsyncFunctionDef),
                        ))
                    elif isinstance(node, ast.ClassDef):
                        result.symbols.append(ParsedSymbol(
                            name=node.name,
                            kind="class",
                            line_start=node.lineno,
                            line_end=node.end_lineno or node.lineno,
                            language=language,
                        ))

            except Exception as e:
                result.errors.append(f"Fallback parse error: {e}")

        return result


# =============================================================================
# API PUBLIQUE
# =============================================================================

def is_tree_sitter_available() -> bool:
    """Vérifie si tree-sitter est disponible."""
    return TreeSitterParser.is_available()


def get_supported_languages() -> list[str]:
    """Retourne la liste des langages supportés."""
    return list(set(EXTENSION_TO_LANGUAGE.values()))


def get_supported_extensions() -> list[str]:
    """Retourne la liste des extensions supportées."""
    return list(EXTENSION_TO_LANGUAGE.keys())


def parse_file(file_path: Path | str) -> ParseResult:
    """
    Parse un fichier et retourne les symboles extraits.

    Args:
        file_path: Chemin du fichier à parser

    Returns:
        ParseResult avec symboles, imports, et appels
    """
    parser = TreeSitterParser()
    return parser.parse_file(file_path)


def parse_content(content: str, language: str) -> ParseResult:
    """
    Parse du contenu directement (sans fichier).

    Args:
        content: Code source à parser
        language: Langage du code

    Returns:
        ParseResult avec symboles extraits
    """
    parser = TreeSitterParser()

    if not parser.is_available():
        return ParseResult(file_path="<string>", language=language,
                          errors=["tree-sitter not available"])

    ts_parser = parser.get_parser(language)
    if not ts_parser:
        return ParseResult(file_path="<string>", language=language,
                          errors=[f"No parser for {language}"])

    try:
        content_bytes = content.encode("utf-8")
        tree = ts_parser.parse(content_bytes)

        result = ParseResult(file_path="<string>", language=language)
        result.symbols = parser._extract_symbols(tree, content_bytes, language)
        result.imports = parser._extract_imports(tree, content_bytes, language)
        result.calls = parser._extract_calls(tree, content_bytes, language)

        return result

    except Exception as e:
        return ParseResult(file_path="<string>", language=language,
                          errors=[str(e)])


__all__ = [
    # Classes
    "TreeSitterParser",
    "ParsedSymbol",
    "ParsedImport",
    "ParsedCall",
    "ParseResult",
    # Functions
    "parse_file",
    "parse_content",
    "is_tree_sitter_available",
    "get_supported_languages",
    "get_supported_extensions",
    # Constants
    "EXTENSION_TO_LANGUAGE",
]
