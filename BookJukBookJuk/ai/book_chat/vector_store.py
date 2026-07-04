"""문서를 청킹하고 임베딩해 코사인 유사도 검색을 제공하는 인메모리 벡터 스토어.

외부 DB 없이 numpy 배열로 관리한다.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from openai import AsyncOpenAI

EMBEDDING_MODEL = "text-embedding-3-small"
MAX_BATCH_SIZE = 100
CHUNK_SIZE = 300        # 청크 당 최대 글자 수 (한국어 기준 약 150 토큰)
CHUNK_OVERLAP = 50      # 청크 간 오버랩 글자 수


@dataclass
class Chunk:
    text: str
    source: str
    doc_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


class VectorStore:
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._matrix: np.ndarray | None = None  # shape (n, dim)

    # ── 인덱싱 ───────────────────────────────────────────────

    def _split_text(self, text: str) -> list[str]:
        """텍스트를 CHUNK_SIZE 글자 단위로 분할한다."""
        if len(text) <= CHUNK_SIZE:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
            start = end - CHUNK_OVERLAP
        return chunks

    async def build(
        self,
        client: AsyncOpenAI,
        raw_docs: list[dict],
    ) -> None:
        """raw_docs 를 청킹 → 임베딩 → 저장한다."""
        self._chunks = []
        texts: list[str] = []

        for doc in raw_docs:
            text = doc.get("text", "").strip()
            if not text:
                continue
            for chunk_text in self._split_text(text):
                chunk = Chunk(
                    text=chunk_text,
                    source=doc.get("source", ""),
                    doc_type=doc.get("doc_type", ""),
                    metadata={k: v for k, v in doc.items() if k not in ("text", "source", "doc_type")},
                )
                self._chunks.append(chunk)
                texts.append(chunk_text)

        if not texts:
            return

        embeddings = await _embed_texts(client, texts)
        vecs = [embeddings[t] for t in texts if t in embeddings]
        if vecs:
            self._matrix = np.stack(vecs).astype(np.float32)

    # ── 검색 ─────────────────────────────────────────────────

    async def search(
        self,
        client: AsyncOpenAI,
        query: str,
        top_k: int = 5,
    ) -> list[SearchResult]:
        if self._matrix is None or len(self._chunks) == 0:
            return []

        query_embs = await _embed_texts(client, [query])
        query_vec = query_embs.get(query)
        if query_vec is None:
            return []

        query_vec = query_vec / (np.linalg.norm(query_vec) + 1e-9)
        norms = np.linalg.norm(self._matrix, axis=1, keepdims=True) + 1e-9
        normed = self._matrix / norms
        scores = normed @ query_vec  # (n,)

        top_idx = np.argsort(scores)[::-1][:top_k]
        return [
            SearchResult(chunk=self._chunks[i], score=float(scores[i]))
            for i in top_idx
        ]

    def __len__(self) -> int:
        return len(self._chunks)


async def _embed_texts(
    client: AsyncOpenAI,
    texts: list[str],
) -> dict[str, np.ndarray]:
    if not texts:
        return {}

    batches = [texts[i: i + MAX_BATCH_SIZE] for i in range(0, len(texts), MAX_BATCH_SIZE)]

    async def _embed_batch(batch: list[str]) -> list[tuple[str, np.ndarray]]:
        resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        return [
            (batch[item.index], np.array(item.embedding, dtype=np.float32))
            for item in resp.data
        ]

    results = await asyncio.gather(*[_embed_batch(b) for b in batches])
    mapping: dict[str, np.ndarray] = {}
    for batch_result in results:
        for text, vec in batch_result:
            mapping[text] = vec
    return mapping
