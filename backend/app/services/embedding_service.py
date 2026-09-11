"""Lazy local sentence embeddings for Module 3."""

from functools import lru_cache
import os
from typing import Sequence

import numpy as np

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def load_embedding_model(model_name: str | None = None):
    from sentence_transformers import SentenceTransformer

    name = model_name or os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    return SentenceTransformer(name)


def generate_embeddings(texts: Sequence[str], batch_size: int = 32) -> np.ndarray:
    """Encode non-empty text in batches and return a 2-D float array."""
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("Embedding input must contain non-empty text")
    model = load_embedding_model()
    return np.asarray(model.encode(
        list(texts), batch_size=batch_size, convert_to_numpy=True,
        normalize_embeddings=False, show_progress_bar=False,
    ), dtype=np.float32)