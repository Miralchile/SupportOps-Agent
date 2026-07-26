"""Tokenization helpers shared by indexing and search.

jieba handles Chinese word segmentation; English words and numbers pass
through unchanged. The output is a lowercase, space-joined token string that
matches the ``whitespace``-analyzed ``*_ltks`` fields in the Elasticsearch
mapping, so index-time and query-time tokenization stay consistent.
"""

from __future__ import annotations

import re
from typing import Iterable, Iterator

import jieba

jieba.setLogLevel(60)  # silence "Building prefix dict" logs

_WORD_RE = re.compile(r"[0-9A-Za-z一-鿿]")


def _clean(tokens: Iterable[str]) -> Iterator[str]:
    for token in tokens:
        token = token.strip().lower()
        if token and _WORD_RE.search(token):
            yield token


def tokenize(text: str | None) -> str:
    """Coarse-grained tokens used for the main ``content_ltks`` field."""
    if not text:
        return ""
    return " ".join(_clean(jieba.cut(str(text))))


def fine_grained_tokenize(text: str | None) -> str:
    """Search-engine style tokens (long words also split into sub-words)."""
    if not text:
        return ""
    return " ".join(_clean(jieba.cut_for_search(str(text))))
