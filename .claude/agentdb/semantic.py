"""
AgentDB Semantic Search Module.

Ce module fournit la recherche sémantique pour AgentDB en utilisant
des embeddings vectoriels générés par sentence-transformers.

Fonctionnalités:
- Génération d'embeddings pour symboles et fichiers
- Recherche par similarité cosinus
- Cache intelligent des requêtes
- Fallback gracieux si sentence-transformers n'est pas installé

Modèle par défaut: all-MiniLM-L6-v2 (384 dimensions, rapide et efficace)
"""

from __future__ import annotations

import hashlib
import json
import logging
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Protocol

import numpy as np

logger = logging.getLogger("agentdb.semantic")

# Configuration par défaut
DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_DIMENSIONS = 384
DEFAULT_TOP_K = 10
DEFAULT_THRESHOLD = 0.3
CACHE_EXPIRY_HOURS = 24


# =============================================================================
# PROTOCOLES ET TYPES
# =============================================================================

class DatabaseProtocol(Protocol):
    """Protocole pour la connexion à la base de données."""

    def execute(self, query: str, params: tuple = ()) -> Any:
        ...

    def executemany(self, query: str, params: list) -> Any:
        ...

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        ...

    def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        ...


@dataclass
class SearchResult:
    """Résultat d'une recherche sémantique."""

    id: int
    name: str
    kind: str
    file_path: str
    similarity: float
    doc_comment: Optional[str] = None
    signature: Optional[str] = None
    module: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "file_path": self.file_path,
            "similarity": round(self.similarity, 4),
            "doc_comment": self.doc_comment,
            "signature": self.signature,
            "module": self.module,
        }


# =============================================================================
# GESTION DU MODÈLE D'EMBEDDINGS
# =============================================================================

class EmbeddingModel:
    """
    Wrapper pour le modèle d'embeddings sentence-transformers.

    Gère le chargement paresseux et le fallback gracieux.
    """

    _instance: Optional["EmbeddingModel"] = None
    _model: Any = None
    _model_name: str = DEFAULT_MODEL
    _available: Optional[bool] = None

    def __new__(cls) -> "EmbeddingModel":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def is_available(cls) -> bool:
        """Vérifie si sentence-transformers est disponible."""
        if cls._available is None:
            try:
                from sentence_transformers import SentenceTransformer  # noqa: F401
                cls._available = True
            except ImportError:
                cls._available = False
                logger.warning(
                    "sentence-transformers non installé. "
                    "Installez avec: pip install sentence-transformers"
                )
        return cls._available

    @classmethod
    def get_model(cls):
        """Retourne le modèle chargé (lazy loading)."""
        if not cls.is_available():
            return None

        if cls._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Chargement du modèle {cls._model_name}...")
            cls._model = SentenceTransformer(cls._model_name)
            logger.info("Modèle chargé.")

        return cls._model

    @classmethod
    def encode(cls, texts: list[str], show_progress: bool = False) -> Optional[np.ndarray]:
        """
        Encode une liste de textes en vecteurs d'embeddings.

        Returns:
            ndarray de shape (n_texts, dimensions) ou None si non disponible
        """
        model = cls.get_model()
        if model is None:
            return None

        if not texts:
            return np.array([])

        return model.encode(
            texts,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
            normalize_embeddings=True,  # Pré-normaliser pour cosinus
        )

    @classmethod
    def encode_single(cls, text: str) -> Optional[np.ndarray]:
        """Encode un seul texte."""
        result = cls.encode([text])
        return result[0] if result is not None and len(result) > 0 else None


# =============================================================================
# UTILITAIRES DE SÉRIALISATION
# =============================================================================

def embedding_to_blob(embedding: np.ndarray) -> bytes:
    """Convertit un embedding numpy en BLOB pour SQLite."""
    return embedding.astype(np.float32).tobytes()


def blob_to_embedding(blob: bytes, dimensions: int = DEFAULT_DIMENSIONS) -> np.ndarray:
    """Convertit un BLOB SQLite en embedding numpy."""
    return np.frombuffer(blob, dtype=np.float32).reshape(-1)


def compute_text_hash(text: str) -> str:
    """Calcule un hash MD5 du texte pour la détection de changements."""
    return hashlib.md5(text.encode()).hexdigest()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calcule la similarité cosinus entre deux vecteurs."""
    # Si les vecteurs sont pré-normalisés, c'est juste le produit scalaire
    return float(np.dot(a, b))


# =============================================================================
# INDEXEUR SÉMANTIQUE
# =============================================================================

class SemanticIndexer:
    """
    Gère l'indexation sémantique des symboles et fichiers.
    """

    def __init__(self, db: DatabaseProtocol):
        self.db = db
        self.model_name = DEFAULT_MODEL
        self.model_version = "1.0"

    def _build_symbol_text(self, symbol: dict) -> str:
        """
        Construit le texte à encoder pour un symbole.

        Combine: nom, signature, documentation
        """
        parts = []

        # Nom qualifié ou simple
        name = symbol.get("qualified_name") or symbol.get("name", "")
        if name:
            parts.append(name)

        # Signature pour les fonctions
        signature = symbol.get("signature")
        if signature:
            parts.append(signature)

        # Documentation
        doc = symbol.get("doc_comment")
        if doc:
            # Nettoyer la doc (enlever les /// ou /** */)
            doc = doc.strip()
            for prefix in ["///", "/**", "*/", "*", "//", "#"]:
                doc = doc.replace(prefix, " ")
            doc = " ".join(doc.split())  # Normaliser les espaces
            if doc:
                parts.append(doc)

        return " ".join(parts)

    def _build_file_text(self, file_info: dict, symbols: list[dict]) -> str:
        """
        Construit le texte à encoder pour un fichier.

        Combine: path, module, docstrings des symboles
        """
        parts = []

        # Module
        module = file_info.get("module")
        if module:
            parts.append(f"Module: {module}")

        # Noms des symboles principaux
        for sym in symbols[:20]:  # Limiter à 20 symboles
            text = self._build_symbol_text(sym)
            if text:
                parts.append(text)

        return " ".join(parts)

    def index_symbols(
        self,
        file_ids: Optional[list[int]] = None,
        force_reindex: bool = False,
        batch_size: int = 100,
        show_progress: bool = True,
    ) -> dict[str, int]:
        """
        Indexe les symboles en générant leurs embeddings.

        Args:
            file_ids: Liste des IDs de fichiers à indexer (None = tous)
            force_reindex: Réindexer même si l'embedding existe
            batch_size: Taille des lots pour l'encodage
            show_progress: Afficher la progression

        Returns:
            Stats: {"indexed": n, "skipped": n, "errors": n}
        """
        if not EmbeddingModel.is_available():
            return {"indexed": 0, "skipped": 0, "errors": 0, "error": "model_unavailable"}

        stats = {"indexed": 0, "skipped": 0, "errors": 0}

        # Récupérer les symboles à indexer
        query = """
            SELECT s.id, s.name, s.qualified_name, s.kind, s.signature, s.doc_comment,
                   se.source_text_hash as existing_hash
            FROM symbols s
            LEFT JOIN symbol_embeddings se ON se.symbol_id = s.id
            WHERE s.kind IN ('function', 'method', 'class', 'struct', 'interface', 'type')
        """
        params = []

        if file_ids:
            placeholders = ",".join("?" * len(file_ids))
            query += f" AND s.file_id IN ({placeholders})"
            params.extend(file_ids)

        if not force_reindex:
            query += " AND se.id IS NULL"

        symbols = self.db.fetch_all(query, tuple(params))

        if not symbols:
            logger.info("Aucun symbole à indexer.")
            return stats

        logger.info(f"Indexation de {len(symbols)} symboles...")

        # Traiter par lots
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]

            # Construire les textes
            texts = []
            valid_symbols = []

            for sym in batch:
                text = self._build_symbol_text(sym)
                text_hash = compute_text_hash(text)

                # Vérifier si le texte a changé
                if not force_reindex and sym.get("existing_hash") == text_hash:
                    stats["skipped"] += 1
                    continue

                if text.strip():
                    texts.append(text)
                    valid_symbols.append((sym, text_hash))
                else:
                    stats["skipped"] += 1

            if not texts:
                continue

            # Encoder le lot
            try:
                embeddings = EmbeddingModel.encode(texts, show_progress=False)
                if embeddings is None:
                    stats["errors"] += len(texts)
                    continue

                # Insérer/mettre à jour en base
                for (sym, text_hash), embedding in zip(valid_symbols, embeddings):
                    self._upsert_symbol_embedding(
                        sym["id"], embedding, text_hash
                    )
                    stats["indexed"] += 1

            except Exception as e:
                logger.error(f"Erreur lors de l'encodage du lot: {e}")
                stats["errors"] += len(texts)

            if show_progress and (i + batch_size) % 500 == 0:
                logger.info(f"  Progression: {i + batch_size}/{len(symbols)}")

        logger.info(
            f"Indexation terminée: {stats['indexed']} indexés, "
            f"{stats['skipped']} ignorés, {stats['errors']} erreurs"
        )
        return stats

    def _upsert_symbol_embedding(
        self, symbol_id: int, embedding: np.ndarray, text_hash: str
    ) -> None:
        """Insère ou met à jour l'embedding d'un symbole."""
        blob = embedding_to_blob(embedding)

        self.db.execute(
            """
            INSERT INTO symbol_embeddings (symbol_id, embedding, model_name, model_version,
                                          dimensions, source_text_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(symbol_id) DO UPDATE SET
                embedding = excluded.embedding,
                model_name = excluded.model_name,
                model_version = excluded.model_version,
                source_text_hash = excluded.source_text_hash,
                updated_at = datetime('now')
            """,
            (symbol_id, blob, self.model_name, self.model_version, DEFAULT_DIMENSIONS, text_hash),
        )

    def index_files(
        self,
        file_ids: Optional[list[int]] = None,
        force_reindex: bool = False,
        show_progress: bool = True,
    ) -> dict[str, int]:
        """
        Indexe les fichiers en générant leurs embeddings.

        Returns:
            Stats: {"indexed": n, "skipped": n, "errors": n}
        """
        if not EmbeddingModel.is_available():
            return {"indexed": 0, "skipped": 0, "errors": 0, "error": "model_unavailable"}

        stats = {"indexed": 0, "skipped": 0, "errors": 0}

        # Récupérer les fichiers à indexer
        query = """
            SELECT f.id, f.path, f.module,
                   fe.source_text_hash as existing_hash
            FROM files f
            LEFT JOIN file_embeddings fe ON fe.file_id = f.id
            WHERE f.file_type = 'source'
        """
        params = []

        if file_ids:
            placeholders = ",".join("?" * len(file_ids))
            query += f" AND f.id IN ({placeholders})"
            params.extend(file_ids)

        if not force_reindex:
            query += " AND fe.id IS NULL"

        files = self.db.fetch_all(query, tuple(params))

        if not files:
            logger.info("Aucun fichier à indexer.")
            return stats

        logger.info(f"Indexation de {len(files)} fichiers...")

        for file_info in files:
            try:
                # Récupérer les symboles du fichier
                symbols = self.db.fetch_all(
                    """
                    SELECT name, qualified_name, kind, signature, doc_comment
                    FROM symbols WHERE file_id = ?
                    ORDER BY line_start
                    """,
                    (file_info["id"],),
                )

                # Construire le texte
                text = self._build_file_text(file_info, symbols)
                text_hash = compute_text_hash(text)

                # Vérifier si le texte a changé
                if not force_reindex and file_info.get("existing_hash") == text_hash:
                    stats["skipped"] += 1
                    continue

                if not text.strip():
                    stats["skipped"] += 1
                    continue

                # Encoder
                embedding = EmbeddingModel.encode_single(text)
                if embedding is None:
                    stats["errors"] += 1
                    continue

                # Insérer en base
                self._upsert_file_embedding(file_info["id"], embedding, text_hash)
                stats["indexed"] += 1

            except Exception as e:
                logger.error(f"Erreur indexation fichier {file_info['path']}: {e}")
                stats["errors"] += 1

        logger.info(
            f"Indexation fichiers terminée: {stats['indexed']} indexés, "
            f"{stats['skipped']} ignorés, {stats['errors']} erreurs"
        )
        return stats

    def _upsert_file_embedding(
        self, file_id: int, embedding: np.ndarray, text_hash: str
    ) -> None:
        """Insère ou met à jour l'embedding d'un fichier."""
        blob = embedding_to_blob(embedding)

        self.db.execute(
            """
            INSERT INTO file_embeddings (file_id, embedding, model_name, model_version,
                                        dimensions, source_text_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(file_id) DO UPDATE SET
                embedding = excluded.embedding,
                model_name = excluded.model_name,
                model_version = excluded.model_version,
                source_text_hash = excluded.source_text_hash,
                updated_at = datetime('now')
            """,
            (file_id, blob, self.model_name, self.model_version, DEFAULT_DIMENSIONS, text_hash),
        )

    def get_stats(self) -> dict:
        """Retourne les statistiques d'indexation."""
        stats = self.db.fetch_all("SELECT * FROM v_embedding_stats")
        return {row["type"]: row for row in stats}


# =============================================================================
# MOTEUR DE RECHERCHE SÉMANTIQUE
# =============================================================================

class SemanticSearchEngine:
    """
    Moteur de recherche sémantique pour AgentDB.
    """

    def __init__(self, db: DatabaseProtocol):
        self.db = db
        self.cache_enabled = True

    def search_symbols(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD,
        kind_filter: Optional[str] = None,
        module_filter: Optional[str] = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Recherche sémantique de symboles.

        Args:
            query: Texte de recherche (description naturelle)
            top_k: Nombre max de résultats
            threshold: Seuil de similarité (0-1)
            kind_filter: Filtrer par type (function, class, etc.)
            module_filter: Filtrer par module
            use_cache: Utiliser le cache

        Returns:
            Dict avec query, results[], stats
        """
        if not EmbeddingModel.is_available():
            return self._fallback_search(query, top_k, kind_filter, module_filter)

        # Vérifier le cache
        cache_key = self._build_cache_key(query, "symbol", kind_filter, module_filter)
        if use_cache and self.cache_enabled:
            cached = self._get_cached_results(cache_key)
            if cached:
                return cached

        # Encoder la requête
        query_embedding = EmbeddingModel.encode_single(query)
        if query_embedding is None:
            return self._fallback_search(query, top_k, kind_filter, module_filter)

        # Récupérer tous les embeddings
        sql = """
            SELECT se.symbol_id, se.embedding, s.name, s.kind, s.qualified_name,
                   s.doc_comment, s.signature, f.path as file_path, f.module
            FROM symbol_embeddings se
            JOIN symbols s ON se.symbol_id = s.id
            JOIN files f ON s.file_id = f.id
            WHERE 1=1
        """
        params = []

        if kind_filter:
            sql += " AND s.kind = ?"
            params.append(kind_filter)

        if module_filter:
            sql += " AND f.module LIKE ?"
            params.append(f"%{module_filter}%")

        rows = self.db.fetch_all(sql, tuple(params))

        if not rows:
            return {
                "query": query,
                "results": [],
                "stats": {"total": 0, "source": "semantic", "cached": False},
            }

        # Calculer les similarités
        results = []
        for row in rows:
            embedding = blob_to_embedding(row["embedding"])
            similarity = cosine_similarity(query_embedding, embedding)

            if similarity >= threshold:
                results.append(
                    SearchResult(
                        id=row["symbol_id"],
                        name=row["name"],
                        kind=row["kind"],
                        file_path=row["file_path"],
                        similarity=similarity,
                        doc_comment=row.get("doc_comment"),
                        signature=row.get("signature"),
                        module=row.get("module"),
                    )
                )

        # Trier par similarité décroissante
        results.sort(key=lambda r: r.similarity, reverse=True)
        results = results[:top_k]

        response = {
            "query": query,
            "results": [r.to_dict() for r in results],
            "stats": {
                "total": len(results),
                "threshold": threshold,
                "source": "semantic",
                "cached": False,
            },
        }

        # Mettre en cache
        if use_cache and self.cache_enabled:
            self._cache_results(cache_key, query, query_embedding, response)

        return response

    def search_files(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD,
        module_filter: Optional[str] = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Recherche sémantique de fichiers.
        """
        if not EmbeddingModel.is_available():
            return {"query": query, "results": [], "stats": {"source": "unavailable"}}

        # Encoder la requête
        query_embedding = EmbeddingModel.encode_single(query)
        if query_embedding is None:
            return {"query": query, "results": [], "stats": {"source": "error"}}

        # Récupérer tous les embeddings de fichiers
        sql = """
            SELECT fe.file_id, fe.embedding, f.path, f.module, f.is_critical,
                   f.lines_code, f.complexity_avg
            FROM file_embeddings fe
            JOIN files f ON fe.file_id = f.id
            WHERE 1=1
        """
        params = []

        if module_filter:
            sql += " AND f.module LIKE ?"
            params.append(f"%{module_filter}%")

        rows = self.db.fetch_all(sql, tuple(params))

        results = []
        for row in rows:
            embedding = blob_to_embedding(row["embedding"])
            similarity = cosine_similarity(query_embedding, embedding)

            if similarity >= threshold:
                results.append({
                    "file_id": row["file_id"],
                    "path": row["path"],
                    "module": row.get("module"),
                    "similarity": round(similarity, 4),
                    "is_critical": bool(row.get("is_critical")),
                    "lines_code": row.get("lines_code"),
                    "complexity_avg": row.get("complexity_avg"),
                })

        results.sort(key=lambda r: r["similarity"], reverse=True)
        results = results[:top_k]

        return {
            "query": query,
            "results": results,
            "stats": {
                "total": len(results),
                "threshold": threshold,
                "source": "semantic",
            },
        }

    def find_similar_symbols(
        self,
        symbol_id: int,
        top_k: int = 10,
        threshold: float = 0.5,
    ) -> list[dict]:
        """
        Trouve les symboles similaires à un symbole donné.
        """
        # Récupérer l'embedding du symbole
        row = self.db.fetch_one(
            "SELECT embedding FROM symbol_embeddings WHERE symbol_id = ?",
            (symbol_id,),
        )

        if not row:
            return []

        source_embedding = blob_to_embedding(row["embedding"])

        # Rechercher les symboles similaires
        rows = self.db.fetch_all(
            """
            SELECT se.symbol_id, se.embedding, s.name, s.kind, f.path
            FROM symbol_embeddings se
            JOIN symbols s ON se.symbol_id = s.id
            JOIN files f ON s.file_id = f.id
            WHERE se.symbol_id != ?
            """,
            (symbol_id,),
        )

        results = []
        for row in rows:
            embedding = blob_to_embedding(row["embedding"])
            similarity = cosine_similarity(source_embedding, embedding)

            if similarity >= threshold:
                results.append({
                    "symbol_id": row["symbol_id"],
                    "name": row["name"],
                    "kind": row["kind"],
                    "file_path": row["path"],
                    "similarity": round(similarity, 4),
                })

        results.sort(key=lambda r: r["similarity"], reverse=True)
        return results[:top_k]

    def _fallback_search(
        self,
        query: str,
        top_k: int,
        kind_filter: Optional[str],
        module_filter: Optional[str],
    ) -> dict[str, Any]:
        """
        Recherche par mots-clés en fallback (si embeddings non disponibles).
        """
        # Construire une recherche LIKE simple
        words = query.lower().split()
        conditions = []
        params = []

        for word in words[:5]:  # Limiter à 5 mots
            conditions.append(
                "(LOWER(s.name) LIKE ? OR LOWER(s.doc_comment) LIKE ?)"
            )
            params.extend([f"%{word}%", f"%{word}%"])

        sql = f"""
            SELECT s.id, s.name, s.kind, s.doc_comment, s.signature, f.path, f.module
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE ({" OR ".join(conditions)})
        """

        if kind_filter:
            sql += " AND s.kind = ?"
            params.append(kind_filter)

        if module_filter:
            sql += " AND f.module LIKE ?"
            params.append(f"%{module_filter}%")

        sql += f" LIMIT {top_k}"

        rows = self.db.fetch_all(sql, tuple(params))

        return {
            "query": query,
            "results": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "kind": row["kind"],
                    "file_path": row["path"],
                    "similarity": 0.5,  # Score fixe pour le fallback
                    "doc_comment": row.get("doc_comment"),
                    "signature": row.get("signature"),
                    "module": row.get("module"),
                }
                for row in rows
            ],
            "stats": {
                "total": len(rows),
                "source": "fallback_keyword",
                "cached": False,
            },
        }

    def _build_cache_key(
        self, query: str, search_type: str, *filters
    ) -> str:
        """Construit une clé de cache."""
        key = f"{search_type}:{query.lower().strip()}"
        for f in filters:
            if f:
                key += f":{f}"
        return hashlib.md5(key.encode()).hexdigest()

    def _get_cached_results(self, cache_key: str) -> Optional[dict]:
        """Récupère les résultats du cache."""
        row = self.db.fetch_one(
            """
            SELECT results_json FROM semantic_search_cache
            WHERE query_hash = ? AND (expires_at IS NULL OR expires_at > datetime('now'))
            """,
            (cache_key,),
        )

        if row:
            # Mettre à jour les stats de hit
            self.db.execute(
                """
                UPDATE semantic_search_cache
                SET hit_count = hit_count + 1, last_hit_at = datetime('now')
                WHERE query_hash = ?
                """,
                (cache_key,),
            )

            result = json.loads(row["results_json"])
            result["stats"]["cached"] = True
            return result

        return None

    def _cache_results(
        self, cache_key: str, query: str, embedding: np.ndarray, results: dict
    ) -> None:
        """Met en cache les résultats."""
        expires = datetime.utcnow() + timedelta(hours=CACHE_EXPIRY_HOURS)

        self.db.execute(
            """
            INSERT OR REPLACE INTO semantic_search_cache
            (query_hash, query_text, query_embedding, results_json, result_count,
             search_type, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                cache_key,
                query,
                embedding_to_blob(embedding),
                json.dumps(results),
                len(results.get("results", [])),
                "symbol",
                expires.isoformat(),
            ),
        )

    def clear_cache(self, expired_only: bool = True) -> int:
        """
        Nettoie le cache.

        Returns:
            Nombre d'entrées supprimées
        """
        if expired_only:
            self.db.execute(
                "DELETE FROM semantic_search_cache WHERE expires_at < datetime('now')"
            )
        else:
            self.db.execute("DELETE FROM semantic_search_cache")

        return self.db.execute("SELECT changes()").fetchone()[0]


# =============================================================================
# API PUBLIQUE
# =============================================================================

def create_indexer(db: DatabaseProtocol) -> SemanticIndexer:
    """Crée un indexeur sémantique."""
    return SemanticIndexer(db)


def create_search_engine(db: DatabaseProtocol) -> SemanticSearchEngine:
    """Crée un moteur de recherche sémantique."""
    return SemanticSearchEngine(db)


def is_semantic_available() -> bool:
    """Vérifie si la recherche sémantique est disponible."""
    return EmbeddingModel.is_available()


__all__ = [
    # Classes
    "SemanticIndexer",
    "SemanticSearchEngine",
    "EmbeddingModel",
    "SearchResult",
    # Factory functions
    "create_indexer",
    "create_search_engine",
    "is_semantic_available",
    # Utilities
    "embedding_to_blob",
    "blob_to_embedding",
    "cosine_similarity",
]
