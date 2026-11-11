"""Lightweight retrieval layer: parsing, tokenization, embeddings, ES hybrid search.

This package provides the retrieval capabilities used by SupportOps:

- doc_parser:  extract text from PDF / DOCX / TXT / MD and split into chunks
- text_utils:  jieba tokenization for the whitespace-analyzed ``*_ltks`` fields
- embedding:   DashScope (OpenAI-compatible) embeddings, optional at runtime
- es_client:   Elasticsearch connection, index bootstrap and bulk writes
- search:      hybrid keyword + vector retrieval with weighted score fusion
- indexer:     file -> chunks -> Elasticsearch pipeline used by doc upload
"""
