"""LLM Zero-shot 콜드스타트 임베딩 (요구사항 3)

신규 도서나 정보가 부족한 도서는 소개글만으로
(장르, 분위기, 독자층, 테마) 태그를 LLM 으로 즉시 추론하고
OpenAI 임베딩을 통해 1536차원 벡터를 생성한다.
"""
from __future__ import annotations

import json
import sys
import os
from dataclasses import dataclass, field

import numpy as np
from openai import AsyncOpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from book_chat.data_collector import BookContext

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# ── 도서 태그 구조 ────────────────────────────────────────────────────────────

_TAG_TOOL = {
    "type": "function",
    "function": {
        "name": "infer_book_tags",
        "description": "도서 소개글을 분석하여 장르/분위기/독자층/테마 태그를 추론합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "genres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "장르 태그 (예: 한국문학, SF, 추리소설, 자기계발 등) 1~3개",
                },
                "moods": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "분위기 태그 (예: 서정적, 긴장감 있는, 따뜻한, 철학적 등) 1~3개",
                },
                "audiences": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "독자층 태그 (예: 성인, 청소년, 직장인, 인문학 독자 등) 1~2개",
                },
                "themes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "핵심 테마 태그 (예: 성장, 사랑, 정체성, 사회 비판 등) 2~4개",
                },
                "similar_to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "유사한 유명 도서명 (옵션) 1~3개",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "태그 추론 전체 신뢰도",
                },
            },
            "required": ["genres", "moods", "audiences", "themes", "confidence"],
        },
    },
}

_SYSTEM_PROMPT = """당신은 도서 큐레이터 전문가입니다.
주어진 도서 정보(소개글, 저자 정보 등)를 바탕으로
장르, 분위기, 독자층, 핵심 테마를 정확하게 분류하세요.
정보가 부족하더라도 소개글에서 최대한 유추하여 태그를 생성하고
신뢰도(confidence)를 낮게 설정하세요."""


@dataclass
class BookTags:
    isbn13: str
    title: str
    genres: list[str] = field(default_factory=list)
    moods: list[str] = field(default_factory=list)
    audiences: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    similar_to: list[str] = field(default_factory=list)
    confidence: float = 0.0
    is_cold_start: bool = False

    def to_embedding_text(self) -> str:
        """임베딩 입력용 텍스트를 생성한다."""
        parts: list[str] = [f"도서: {self.title}"]
        if self.genres:
            parts.append(f"장르: {', '.join(self.genres)}")
        if self.moods:
            parts.append(f"분위기: {', '.join(self.moods)}")
        if self.audiences:
            parts.append(f"독자층: {', '.join(self.audiences)}")
        if self.themes:
            parts.append(f"테마: {', '.join(self.themes)}")
        if self.similar_to:
            parts.append(f"유사 도서: {', '.join(self.similar_to)}")
        return " | ".join(parts)

    def all_tags(self) -> list[str]:
        return self.genres + self.moods + self.audiences + self.themes


# ── ColdStartEmbedder ─────────────────────────────────────────────────────────


class ColdStartEmbedder:
    """소개글만으로 책 벡터를 즉시 생성하는 콜드스타트 임베더.

    처리 흐름:
    1. BookContext → LLM Function Calling → BookTags (장르/분위기/독자층/테마)
    2. BookTags.to_embedding_text() → OpenAI Embedding → 1536차원 벡터
    3. 정규화 후 벡터 반환
    """

    COLD_START_THRESHOLD = 3  # 키워드가 이 개수 미만이면 콜드스타트 처리

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        tag_model: str = "gpt-4o-mini",
    ) -> None:
        self.client = openai_client
        self.tag_model = tag_model

    def is_cold_start(self, ctx: BookContext) -> bool:
        """정보가 부족한 도서인지 판단한다."""
        has_keywords = len(ctx.keywords) >= self.COLD_START_THRESHOLD
        has_description = bool(ctx.description and len(ctx.description) > 50)
        return not (has_keywords and has_description)

    async def infer_book_tags(self, ctx: BookContext) -> BookTags:
        """LLM 으로 도서 태그를 추론한다."""
        input_text = self._build_input(ctx)

        try:
            response = await self.client.chat.completions.create(
                model=self.tag_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": input_text},
                ],
                tools=[_TAG_TOOL],
                tool_choice={"type": "function", "function": {"name": "infer_book_tags"}},
                temperature=0.2,
            )
            tool_call = response.choices[0].message.tool_calls[0]
            raw = json.loads(tool_call.function.arguments)

        except Exception as e:
            print(f"[WARN] 태그 추론 실패 ({ctx.title}): {e}")
            raw = self._fallback_tags(ctx)

        return BookTags(
            isbn13=ctx.isbn13,
            title=ctx.title,
            genres=raw.get("genres", []),
            moods=raw.get("moods", []),
            audiences=raw.get("audiences", []),
            themes=raw.get("themes", []),
            similar_to=raw.get("similar_to", []),
            confidence=float(raw.get("confidence", 0.5)),
            is_cold_start=self.is_cold_start(ctx),
        )

    def _build_input(self, ctx: BookContext) -> str:
        parts: list[str] = [f"제목: {ctx.title}"]
        if ctx.authors:
            parts.append(f"저자: {ctx.authors}")
        if ctx.kdc_class:
            parts.append(f"KDC 분류: {ctx.kdc_class}")
        if ctx.description:
            parts.append(f"소개글: {ctx.description[:600]}")
        if ctx.author_bio:
            parts.append(f"저자 소개: {ctx.author_bio[:300]}")
        if ctx.keywords:
            kw_text = ", ".join(kw.word for kw in ctx.keywords[:10])
            parts.append(f"키워드: {kw_text}")
        if ctx.wiki_book_summary:
            parts.append(f"Wikipedia: {ctx.wiki_book_summary[:400]}")
        return "\n".join(parts)

    def _fallback_tags(self, ctx: BookContext) -> dict:
        """LLM 실패 시 KDC 분류와 키워드 기반 폴백."""
        genres = [ctx.kdc_class] if ctx.kdc_class else ["일반"]
        themes = [kw.word for kw in ctx.keywords[:3]] if ctx.keywords else ["도서"]
        return {
            "genres": genres,
            "moods": ["일반적"],
            "audiences": ["성인"],
            "themes": themes,
            "similar_to": [],
            "confidence": 0.3,
        }

    async def embed_tags(self, tags: BookTags) -> np.ndarray:
        """태그 텍스트를 임베딩 벡터로 변환한다."""
        text = tags.to_embedding_text()
        response = await self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[text],
        )
        vec = np.array(response.data[0].embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    async def embed_cold_book(self, ctx: BookContext) -> tuple[np.ndarray, BookTags]:
        """콜드스타트 책의 임베딩 벡터와 태그를 생성한다.

        Returns:
            (정규화된 1536차원 벡터, BookTags)
        """
        tags = await self.infer_book_tags(ctx)
        vector = await self.embed_tags(tags)
        return vector, tags

    async def embed_rich_book(self, ctx: BookContext) -> np.ndarray:
        """키워드/설명이 풍부한 책의 임베딩 벡터를 생성한다.

        키워드 가중 평균 + 긴 텍스트(소개/요약) 임베딩을 혼합한다.

        설계 의도:
        - 긴 서술 텍스트(소개/위키 요약)는 "임베딩"에만 반영한다. (KG 노드로 확장 금지)
        - 짧고 정규화 가능한 정보(키워드)는 벡터에 가중 반영하되 과도한 키워드 폭증은 제한한다.
        """
        texts_to_embed: list[str] = []
        weights: list[float] = []

        # 소개글 임베딩
        if ctx.description:
            texts_to_embed.append(ctx.description[:500])
            weights.append(0.45)

        # Wikipedia 요약 임베딩 (길지만 의미 밀도가 높아 벡터에만 반영)
        if ctx.wiki_book_summary:
            texts_to_embed.append(ctx.wiki_book_summary[:450])
            weights.append(0.15)

        # 키워드 임베딩 (상위 10개, 가중치 적용)
        for kw in ctx.keywords[:10]:
            texts_to_embed.append(kw.word)
            weights.append(kw.weight * 0.40)

        if not texts_to_embed:
            # 폴백: 제목만 임베딩
            texts_to_embed = [ctx.title]
            weights = [1.0]

        response = await self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts_to_embed,
        )
        vecs = [np.array(item.embedding, dtype=np.float32) for item in response.data]
        w_arr = np.array(weights, dtype=np.float32)
        w_arr /= w_arr.sum()

        combined = sum(w * v for w, v in zip(w_arr, vecs))
        norm = np.linalg.norm(combined)
        if norm > 0:
            combined /= norm
        return combined

    async def get_book_vector(self, ctx: BookContext) -> tuple[np.ndarray, bool]:
        """도서 벡터를 반환한다. 콜드스타트 여부도 함께 반환.

        Returns:
            (vector, is_cold_start)
        """
        if self.is_cold_start(ctx):
            vec, _ = await self.embed_cold_book(ctx)
            return vec, True
        else:
            vec = await self.embed_rich_book(ctx)
            return vec, False
