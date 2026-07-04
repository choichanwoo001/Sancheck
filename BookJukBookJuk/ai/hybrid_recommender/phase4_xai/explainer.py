"""XAI: KG 경로 기반 추천 이유 자연어 생성 (요구사항 6)

블랙박스 문제 해결:
1. RippleNet 이 탐색한 KG 경로를 추출한다
   예: User → [채식주의자] → [한강] → [소년이 온다]
2. 경로를 LLM 에게 전달해 자연어 설명으로 변환한다
   예: "당신이 좋아하는 '채식주의자'의 저자 한강의 다른 작품입니다."
"""
from __future__ import annotations

import sys
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from ..phase1_kg.kg_store import NetworkXKGStore
    from ..phase3_scoring.hybrid_scorer import ScoredBook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ── 데이터클래스 ──────────────────────────────────────────────────────────────


@dataclass
class ExplainedRecommendation:
    """추천 이유가 포함된 최종 추천 결과."""
    isbn13: str
    title: str
    authors: str
    final_score: float
    graph_score: float
    vector_score: float
    alpha_used: float
    kdc_class: str = ""
    publisher: str = ""
    published_year: str = ""
    explanation: str = ""                          # LLM 생성 자연어 설명
    kg_paths: list[list[tuple[str, str, str]]] = field(default_factory=list)  # KG 경로들
    seed_books_used: list[str] = field(default_factory=list)  # 연결된 시드 책 제목

    def __str__(self) -> str:
        lines = [
            f"📚 {self.title}",
            f"   저자: {self.authors}",
            f"   점수: {self.final_score:.3f} (graph={self.graph_score:.3f}, vec={self.vector_score:.3f})",
        ]
        if self.explanation:
            lines.append(f"   💡 {self.explanation}")
        return "\n".join(lines)


# ── KG 경로 추출기 ────────────────────────────────────────────────────────────


class KGPathExtractor:
    """사용자 이력과 추천 도서 사이의 KG 연결 경로를 추출한다."""

    def __init__(self, kg_store: "NetworkXKGStore", max_hops: int = 3) -> None:
        self.kg = kg_store
        self.max_hops = max_hops

    def find_explanation_paths(
        self,
        seed_isbns: list[str],
        recommended_isbn: str,
        max_paths: int = 3,
    ) -> list[list[tuple[str, str, str]]]:
        """시드 책들과 추천 책 사이의 설명 경로를 탐색한다.

        Args:
            seed_isbns: 사용자가 읽은 책 ISBN 목록
            recommended_isbn: 추천된 책 ISBN
            max_paths: 반환할 최대 경로 수

        Returns:
            [[(head_label, relation, tail_label), ...], ...] 형태의 경로 목록
        """
        dst_id = f"book:{recommended_isbn}"
        paths: list[list[tuple[str, str, str]]] = []

        for isbn in seed_isbns:
            src_id = f"book:{isbn}"
            if src_id == dst_id:
                continue

            path_triples = self.kg.find_explanation_path(
                src_id, dst_id, max_hops=self.max_hops
            )
            if path_triples:
                paths.append(path_triples)
                if len(paths) >= max_paths:
                    break

        # 직접 경로가 없으면 간접 경로 시도 (공통 저자/테마)
        if not paths:
            indirect = self._find_indirect_paths(seed_isbns, recommended_isbn)
            paths.extend(indirect[:max_paths])

        return paths

    def _find_indirect_paths(
        self,
        seed_isbns: list[str],
        recommended_isbn: str,
    ) -> list[list[tuple[str, str, str]]]:
        """공통 중간 노드(저자/테마/개념)를 통한 간접 경로를 탐색한다."""
        dst_id = f"book:{recommended_isbn}"
        dst_neighbors = {n for n, _, _ in self.kg.get_neighbors(dst_id)}

        indirect_paths: list[list[tuple[str, str, str]]] = []

        for isbn in seed_isbns:
            src_id = f"book:{isbn}"
            src_neighbors = {n for n, _, _ in self.kg.get_neighbors(src_id)}

            # 공통 이웃 (저자, 테마, 개념 등)
            common = src_neighbors & dst_neighbors
            for common_node in list(common)[:2]:
                # src → common → dst 경로 구성
                src_label = self.kg.get_label(src_id)
                common_label = self.kg.get_label(common_node)
                dst_label = self.kg.get_label(dst_id)

                src_neighbors_data = self.kg.get_neighbors(src_id)
                src_rel = next(
                    (rel for n, rel, _ in src_neighbors_data if n == common_node),
                    "RELATED_TO"
                )
                dst_neighbors_data = self.kg.get_neighbors(dst_id)
                dst_rel = next(
                    (rel for n, rel, _ in dst_neighbors_data if n == common_node),
                    "RELATED_TO"
                )

                path = [
                    (src_label, src_rel, common_label),
                    (dst_label, dst_rel, common_label),
                ]
                indirect_paths.append(path)

        return indirect_paths

    def extract_key_connection(
        self,
        paths: list[list[tuple[str, str, str]]],
    ) -> str:
        """경로에서 핵심 연결 요소를 추출해 요약 텍스트로 변환한다."""
        if not paths:
            return ""

        path = paths[0]
        if not path:
            return ""

        # 관계 유형에 따른 설명 템플릿
        rel_descriptions = {
            "WRITTEN_BY": "{tail}이(가) 저자인",
            "EXPLORES": "{tail} 주제를 다루는",
            "SET_IN": "{tail} 시대/배경의",
            "HAS_CHARACTER": "{tail} 등장인물이 나오는",
            "INFLUENCED_BY": "{tail}의 영향을 받은",
            "SIMILAR_TO": "{tail}과 유사한",
            "AWARDED": "{tail} 수상작",
            "PART_OF_SERIES": "{tail} 시리즈",
        }

        parts: list[str] = []
        for head, rel, tail in path:
            if rel in rel_descriptions:
                desc = rel_descriptions[rel].format(head=head, tail=tail)
                parts.append(desc)

        return ", ".join(parts) if parts else str(path[0])


# ── LLM 추천 이유 생성기 ─────────────────────────────────────────────────────


_EXPLANATION_SYSTEM_PROMPT = """당신은 도서 추천 큐레이터입니다.
사용자가 좋아하는 책과 새로 추천하는 책 사이의 연결 관계를 분석하여,
왜 이 책을 추천하는지 1~2문장의 친근하고 명확한 설명을 작성하세요.

설명 작성 원칙:
- 구체적인 연결 고리(저자, 테마, 분위기, 시대)를 언급하세요
- "이 책은..." 또는 "당신이 좋아하는 ~처럼..." 형태로 시작하세요
- 너무 기술적이지 않게, 독자가 쉽게 이해할 수 있도록 작성하세요
- 50~80자 이내로 간결하게 작성하세요"""

_EXPLANATION_PROMPT_TEMPLATE = """[사용자가 읽은 책]
{seed_books}

[추천하는 책]
제목: {recommended_title}
저자: {recommended_authors}
분류: {kdc_class}

[KG 연결 경로]
{kg_paths_text}

[추천 이유 생성]
위 정보를 바탕으로 이 책을 추천하는 이유를 1~2문장으로 설명하세요."""


class RecommendationExplainer:
    """KG 경로를 LLM 으로 자연어 추천 이유로 변환한다.

    Args:
        openai_client: AsyncOpenAI 클라이언트
        kg_store: KG 저장소 (경로 탐색용)
        model: 사용할 LLM 모델명
    """

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        kg_store: "NetworkXKGStore",
        model: str = "gpt-4o-mini",
    ) -> None:
        self.client = openai_client
        self.kg = kg_store
        self.model = model
        self.path_extractor = KGPathExtractor(kg_store)

    def _format_kg_paths(
        self,
        paths: list[list[tuple[str, str, str]]],
    ) -> str:
        """KG 경로를 읽기 좋은 텍스트로 변환한다."""
        if not paths:
            return "직접 연결 경로 없음"

        lines: list[str] = []
        for i, path in enumerate(paths[:3], 1):
            path_str = " → ".join(
                f"{head} -[{rel}]→ {tail}" for head, rel, tail in path
            )
            lines.append(f"경로 {i}: {path_str}")
        return "\n".join(lines)

    def _format_seed_books(
        self,
        seed_isbns: list[str],
        seed_book_titles: dict[str, str],
    ) -> str:
        """시드 책 목록을 텍스트로 변환한다."""
        parts: list[str] = []
        for isbn in seed_isbns[:5]:
            title = seed_book_titles.get(isbn, isbn)
            parts.append(f"- {title}")
        return "\n".join(parts) if parts else "이력 없음"

    async def explain(
        self,
        recommended: "ScoredBook",
        seed_isbns: list[str],
        seed_book_titles: dict[str, str],
    ) -> tuple[str, list[list[tuple[str, str, str]]]]:
        """추천 이유와 KG 경로를 생성한다.

        Args:
            recommended: 추천된 책 (ScoredBook)
            seed_isbns: 사용자 시드 ISBN 목록
            seed_book_titles: {isbn: title} 매핑

        Returns:
            (자연어 설명, KG 경로 목록)
        """
        # KG 경로 추출
        kg_paths = self.path_extractor.find_explanation_paths(
            seed_isbns=seed_isbns,
            recommended_isbn=recommended.isbn13,
        )

        # 경로가 없거나 간단한 경우 규칙 기반 설명으로 폴백
        if not kg_paths:
            fallback = self._rule_based_explanation(recommended, seed_book_titles)
            return fallback, []

        # LLM 으로 자연어 설명 생성
        prompt = _EXPLANATION_PROMPT_TEMPLATE.format(
            seed_books=self._format_seed_books(seed_isbns, seed_book_titles),
            recommended_title=recommended.title,
            recommended_authors=recommended.authors,
            kdc_class=recommended.kdc_class or "미분류",
            kg_paths_text=self._format_kg_paths(kg_paths),
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _EXPLANATION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=150,
            )
            explanation = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[WARN] 설명 생성 실패 ({recommended.title}): {e}")
            explanation = self._rule_based_explanation(recommended, seed_book_titles)

        return explanation, kg_paths

    def _rule_based_explanation(
        self,
        book: "ScoredBook",
        seed_book_titles: dict[str, str],
    ) -> str:
        """LLM 없이 규칙 기반 설명을 생성한다."""
        if book.vector_score > book.graph_score:
            if seed_book_titles:
                seed_title = next(iter(seed_book_titles.values()))
                return f"'{seed_title}'과 비슷한 분위기와 주제를 다루는 작품입니다."
            return "유사한 독서 취향을 가진 독자들이 선택한 작품입니다."
        else:
            if book.authors:
                return f"당신이 관심 가질 만한 {book.authors}의 추천 도서입니다."
            return "KG 분석 결과 당신의 독서 패턴과 연결된 작품입니다."

    async def explain_batch(
        self,
        recommendations: list["ScoredBook"],
        seed_isbns: list[str],
        seed_book_titles: dict[str, str],
        top_k: int = 10,
    ) -> list[ExplainedRecommendation]:
        """여러 추천 결과를 일괄 처리한다.

        Args:
            recommendations: 추천 도서 목록
            seed_isbns: 사용자 시드 ISBN 목록
            seed_book_titles: {isbn: title} 매핑
            top_k: 설명을 생성할 상위 도서 수

        Returns:
            ExplainedRecommendation 목록
        """
        import asyncio

        async def _explain_one(book: "ScoredBook") -> ExplainedRecommendation:
            explanation, kg_paths = await self.explain(
                book, seed_isbns, seed_book_titles
            )
            seed_used = []
            for isbn in seed_isbns[:3]:
                for path in kg_paths:
                    if seed_book_titles.get(isbn, isbn) in str(path):
                        seed_used.append(seed_book_titles.get(isbn, isbn))
                        break

            return ExplainedRecommendation(
                isbn13=book.isbn13,
                title=book.title,
                authors=book.authors,
                final_score=book.final_score,
                graph_score=book.graph_score,
                vector_score=book.vector_score,
                alpha_used=book.alpha_used,
                kdc_class=book.kdc_class,
                publisher=book.publisher,
                published_year=book.published_year,
                explanation=explanation,
                kg_paths=kg_paths,
                seed_books_used=seed_used,
            )

        tasks = [_explain_one(book) for book in recommendations[:top_k]]
        return await asyncio.gather(*tasks)
