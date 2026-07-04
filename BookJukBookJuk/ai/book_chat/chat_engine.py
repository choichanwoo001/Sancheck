"""책 토론 채팅 엔진.

관련성 가드 → 하이브리드 검색 → LLM 답변 생성 흐름을 관리한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from .data_collector import BookContext, collect_book_context
from .graph_builder import KnowledgeGraph, build_knowledge_graph
from .vector_store import VectorStore
from .retriever import HybridRetriever
from .prompts import (
    ANSWER_PROMPT_TEMPLATE,
    REJECTION_MESSAGE,
    RELEVANCE_CHECK_PROMPT,
    SYSTEM_PROMPT_TEMPLATE,
)


@dataclass
class Message:
    role: str   # "user" | "assistant"
    content: str


class ChatSession:
    """책 한 권에 대한 채팅 세션을 관리한다."""

    def __init__(
        self,
        ctx: BookContext,
        kg: KnowledgeGraph,
        vs: VectorStore,
        openai_client: AsyncOpenAI,
    ) -> None:
        self.ctx = ctx
        self.kg = kg
        self.vs = vs
        self.client = openai_client
        self.retriever = HybridRetriever(kg, vs, openai_client)
        self.history: list[Message] = []
        self._system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            title=ctx.title,
            authors=ctx.authors or "미상",
            publisher=ctx.publisher or "미상",
            published_year=ctx.published_year or "미상",
            kdc_class=ctx.kdc_class or "미상",
        )

    async def _is_relevant(self, question: str) -> bool:
        """질문이 현재 책과 관련 있는지 LLM 으로 판정한다."""
        prompt = RELEVANCE_CHECK_PROMPT.format(
            title=self.ctx.title,
            authors=self.ctx.authors or "미상",
            question=question,
        )
        resp = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=5,
        )
        answer = resp.choices[0].message.content.strip().upper()
        return answer.startswith("Y")

    async def chat(self, question: str) -> str:
        """사용자 질문을 받아 답변 문자열을 반환한다."""
        # 1) 관련성 가드
        if not await self._is_relevant(question):
            return REJECTION_MESSAGE.format(title=self.ctx.title)

        # 2) 하이브리드 검색 (그래프 + 벡터 동시 실행)
        ctx_retrieved = await self.retriever.retrieve(question)
        context_text = ctx_retrieved.to_prompt_text()

        # 3) 답변 생성 메시지 구성
        user_content = ANSWER_PROMPT_TEMPLATE.format(
            context=context_text,
            question=question,
        )
        messages: list[dict] = [{"role": "system", "content": self._system_prompt}]

        # 최근 대화 히스토리 (최대 6턴 = 12메시지)
        for msg in self.history[-12:]:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": user_content})

        resp = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        answer = resp.choices[0].message.content.strip()

        # 히스토리 기록 (원본 질문만 저장해 컨텍스트 토큰 절약)
        self.history.append(Message(role="user", content=question))
        self.history.append(Message(role="assistant", content=answer))

        return answer

    def reset_history(self) -> None:
        """대화 히스토리를 초기화한다."""
        self.history.clear()


async def create_session(
    isbn13: str | None = None,
    title: str | None = None,
    author: str | None = None,
    openai_api_key: str | None = None,
    library_api_key: str | None = None,
    aladin_api_key: str | None = None,
) -> ChatSession:
    """책 정보를 수집하고 그래프·벡터 스토어를 구축해 ChatSession 을 반환한다."""
    openai_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
    lib_key = library_api_key or os.getenv("LIBRARY_API_KEY", "")
    aladin_key = aladin_api_key or os.getenv("ALADIN_API_KEY", "")

    client = AsyncOpenAI(api_key=openai_key)

    print("[1/4] 데이터 수집 중 (정보나루 / 알라딘 / Wikipedia)...")
    ctx = await collect_book_context(
        isbn13=isbn13,
        title=title,
        author=author,
        library_api_key=lib_key,
        aladin_api_key=aladin_key,
    )
    print(f"      책: {ctx.title} / 저자: {ctx.authors}")
    print(f"      원문 문서 {len(ctx.raw_docs)}개 수집 완료")

    print("[2/4] 지식 그래프 구축 중...")
    kg = build_knowledge_graph(ctx)
    print(f"      그래프: {kg.summary()}")

    print("[3/4] 벡터 스토어 구축 중 (임베딩 생성)...")
    vs = VectorStore()
    await vs.build(client, ctx.raw_docs)
    print(f"      벡터 스토어: 청크 {len(vs)}개 인덱싱 완료")

    print("[4/4] 채팅 세션 준비 완료!\n")
    return ChatSession(ctx=ctx, kg=kg, vs=vs, openai_client=client)
