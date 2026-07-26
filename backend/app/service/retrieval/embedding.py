"""DashScope (OpenAI-compatible) embedding client.

Embeddings are optional: without a valid API key every call returns ``None``
placeholders and retrieval degrades gracefully to keyword-only search.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Union

from openai import OpenAI

from service.supportops.tools import clean_env_value, has_valid_dashscope_key

logger = logging.getLogger("supportops.embedding")

EMBEDDING_DIMENSIONS = 1024
MAX_BATCH_SIZE = 10  # DashScope caps embedding batches at 10 inputs.

Vector = List[float]


def embedding_vector_field() -> str:
    """Name of the dense-vector field in the Elasticsearch mapping."""
    return f"q_{EMBEDDING_DIMENSIONS}_vec"


def generate_embedding(
    text: Union[str, List[str]],
) -> Union[Optional[Vector], List[Optional[Vector]]]:
    """Embed one text (returns a vector or ``None``) or a list of texts
    (returns one entry per input, ``None`` where embedding failed)."""
    api_key = clean_env_value("DASHSCOPE_API_KEY")
    if not has_valid_dashscope_key(api_key):
        return [None] * len(text) if isinstance(text, list) else None

    client = OpenAI(api_key=api_key, base_url=clean_env_value("DASHSCOPE_BASE_URL"))
    model_name = clean_env_value("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")

    if isinstance(text, str):
        vectors = _embed_batch(client, model_name, [text])
        return vectors[0]

    results: List[Optional[Vector]] = []
    for offset in range(0, len(text), MAX_BATCH_SIZE):
        results.extend(_embed_batch(client, model_name, text[offset:offset + MAX_BATCH_SIZE]))
    return results


def _embed_batch(client: OpenAI, model_name: str, batch: List[str]) -> List[Optional[Vector]]:
    try:
        completion = client.embeddings.create(
            model=model_name,
            input=batch,
            dimensions=EMBEDDING_DIMENSIONS,
            encoding_format="float",
        )
        return [item.embedding for item in completion.data]
    except Exception as exc:
        logger.warning("Embedding request failed (%d texts): %s", len(batch), exc)
        return [None] * len(batch)
