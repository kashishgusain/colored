"""Embedding providers. Real semantic search uses Sentence Transformers.

`test_hash` is a deterministic bag-of-words embedder used ONLY by the automated tests so that
the ChromaDB code path can be exercised without downloading a model. It is not semantic.
"""
import hashlib
import math
import re
import threading

from flask import current_app

from .errors import NotConfigured, ServiceError

TOKEN_RE = re.compile(r"[\w\u0900-\u0963\u0966-\u097F]+", re.UNICODE)
_lock = threading.Lock()
_st_models = {}


class HashEmbedder:
    name = "test_hash_256"
    dim = 256

    def encode(self, texts):
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in TOKEN_RE.findall(text.lower()):
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
                vec[h % self.dim] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        self.name = model_name
        self._model = None

    def _load(self):
        with _lock:
            if self._model is None:
                if self.name in _st_models:
                    self._model = _st_models[self.name]
                    return self._model
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise NotConfigured("sentence-transformers is not installed: pip install sentence-transformers",
                                        code="ST_MISSING") from exc
                try:
                    self._model = SentenceTransformer(self.name)
                except Exception as exc:
                    raise ServiceError(
                        f"The embedding model '{self.name}' could not be loaded ({type(exc).__name__}). "
                        "The first run downloads it from huggingface.co; check your internet connection. "
                        "Keyword search keeps working in the meantime.", code="EMBEDDING_MODEL_LOAD_FAILED") from exc
                _st_models[self.name] = self._model
        return self._model

    def encode(self, texts):
        model = self._load()
        vecs = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]


def get_embedder():
    provider = current_app.config["EMBEDDING_PROVIDER"]
    if provider == "sentence_transformers":
        return SentenceTransformerEmbedder(current_app.config["EMBEDDING_MODEL"])
    if provider == "test_hash":
        return HashEmbedder()
    raise NotConfigured("Semantic search is disabled (EMBEDDING_PROVIDER=none). Keyword search is still available.",
                        code="EMBEDDINGS_DISABLED")
