"""BookContext 에서 NetworkX 지식 그래프를 구축한다.

노드 타입: Book, Author, Character, Theme, HistoricalPeriod, Concept, Publisher
엣지:      WRITTEN_BY, HAS_CHARACTER, KNOWS, SET_IN, EXPLORES, PUBLISHED_BY
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from .data_collector import BookContext


@dataclass
class KnowledgeGraph:
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)

    def add_node(self, node_id: str, node_type: str, **attrs: Any) -> None:
        self.graph.add_node(node_id, type=node_type, **attrs)

    def add_edge(self, src: str, dst: str, relation: str, **attrs: Any) -> None:
        self.graph.add_edge(src, dst, relation=relation, **attrs)

    def get_facts(self, node_id: str, hops: int = 2) -> list[str]:
        """node_id 로부터 최대 hops 홉 범위의 팩트 문자열 목록을 반환한다."""
        if node_id not in self.graph:
            return []

        facts: list[str] = []
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(node_id, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > hops:
                continue
            visited.add(current)

            node_data = self.graph.nodes[current]
            label = node_data.get("label", current)
            desc = node_data.get("description", "")
            if desc:
                facts.append(f"[{node_data.get('type', '')}] {label}: {desc}")

            for _, neighbor, edge_data in self.graph.out_edges(current, data=True):
                rel = edge_data.get("relation", "")
                n_label = self.graph.nodes[neighbor].get("label", neighbor)
                facts.append(f"{label} --[{rel}]--> {n_label}")
                if depth + 1 <= hops:
                    queue.append((neighbor, depth + 1))

        return facts

    def find_matching_nodes(self, query: str) -> list[str]:
        """쿼리 문자열에 label 이 포함된 노드 ID 목록을 반환한다."""
        query_lower = query.lower()
        matched: list[str] = []
        for node_id, data in self.graph.nodes(data=True):
            label = data.get("label", node_id).lower()
            if label in query_lower or any(
                token in query_lower for token in label.split() if len(token) > 1
            ):
                matched.append(node_id)
        return matched

    def summary(self) -> str:
        return (
            f"노드 {self.graph.number_of_nodes()}개, "
            f"엣지 {self.graph.number_of_edges()}개"
        )


def _extract_author_names(authors_str: str) -> list[str]:
    """'홍길동 (지은이), 김영희 (옮긴이)' 형태에서 이름만 추출한다."""
    names = re.split(r"[,;|]", authors_str)
    cleaned: list[str] = []
    for name in names:
        name = re.sub(r"\(.*?\)|（.*?）", "", name).strip()
        if name and len(name) > 1:
            cleaned.append(name)
    return cleaned


def _extract_year_from_text(text: str) -> str:
    match = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", text)
    return match.group(1) if match else ""


def build_knowledge_graph(ctx: BookContext) -> KnowledgeGraph:
    """BookContext 에서 지식 그래프를 구축한다."""
    kg = KnowledgeGraph()
    book_id = f"book:{ctx.isbn13 or ctx.title}"

    # ── Book 노드 ──────────────────────────────────────────────
    kg.add_node(
        book_id,
        node_type="Book",
        label=ctx.title,
        description=(ctx.description or ctx.wiki_book_summary)[:300],
        isbn13=ctx.isbn13,
        published_year=ctx.published_year,
        kdc_class=ctx.kdc_class,
    )

    # ── Author 노드 ────────────────────────────────────────────
    author_names = _extract_author_names(ctx.authors) if ctx.authors else []
    for author_name in author_names:
        author_id = f"author:{author_name}"
        bio_snippet = (ctx.wiki_author_summary or ctx.author_bio)[:300]
        kg.add_node(
            author_id,
            node_type="Author",
            label=author_name,
            description=bio_snippet,
        )
        kg.add_edge(book_id, author_id, relation="WRITTEN_BY")

    # ── Publisher 노드 ─────────────────────────────────────────
    if ctx.publisher:
        pub_id = f"publisher:{ctx.publisher}"
        kg.add_node(pub_id, node_type="Publisher", label=ctx.publisher)
        kg.add_edge(book_id, pub_id, relation="PUBLISHED_BY")

    # ── 정보나루 키워드 → Concept 노드 (상위 20개) ─────────────
    for kw in ctx.keywords[:20]:
        concept_id = f"concept:{kw.word}"
        kg.add_node(concept_id, node_type="Concept", label=kw.word, weight=kw.weight)
        kg.add_edge(book_id, concept_id, relation="EXPLORES", weight=kw.weight)

    # ── Wikipedia 섹션에서 인물·시대배경·테마 추출 ─────────────
    _enrich_from_wiki_sections(kg, book_id, ctx)

    return kg


def _enrich_from_wiki_sections(
    kg: KnowledgeGraph,
    book_id: str,
    ctx: BookContext,
) -> None:
    """Wikipedia 섹션을 파싱해 인물·시대·테마 노드를 추가한다."""
    character_keywords = {"등장인물", "인물", "characters", "cast", "protagonists", "등장"}
    period_keywords = {"배경", "시대", "역사", "background", "setting", "historical", "시대적"}
    theme_keywords = {"주제", "테마", "themes", "motif", "상징", "주제 의식"}

    for sec in ctx.wiki_extra_sections:
        sec_title_lower = sec["title"].lower()
        text = sec["text"]

        if any(k in sec_title_lower for k in character_keywords):
            for line in text.split("\n")[:20]:
                line = line.strip(" -·•*")
                if 2 < len(line) < 50:
                    char_id = f"character:{line[:30]}"
                    if char_id not in kg.graph:
                        kg.add_node(char_id, node_type="Character", label=line[:30], description="")
                    kg.add_edge(book_id, char_id, relation="HAS_CHARACTER")

        elif any(k in sec_title_lower for k in period_keywords):
            year = _extract_year_from_text(text)
            period_id = f"period:{sec['title']}"
            kg.add_node(
                period_id,
                node_type="HistoricalPeriod",
                label=sec["title"],
                description=text[:200],
                year=year,
            )
            kg.add_edge(book_id, period_id, relation="SET_IN")

        elif any(k in sec_title_lower for k in theme_keywords):
            theme_id = f"theme:{sec['title']}"
            kg.add_node(
                theme_id,
                node_type="Theme",
                label=sec["title"],
                description=text[:200],
            )
            kg.add_edge(book_id, theme_id, relation="EXPLORES")

    # 책 요약에서 연도 기반 시대 노드 추가
    if ctx.wiki_book_summary:
        year = _extract_year_from_text(ctx.wiki_book_summary)
        if year:
            period_id = f"period:{year}년대"
            if period_id not in kg.graph:
                kg.add_node(period_id, node_type="HistoricalPeriod", label=f"{year}년대", year=year)
            kg.add_edge(book_id, period_id, relation="SET_IN")

    # KDC 분류명을 Theme 으로 추가
    if ctx.kdc_class:
        theme_id = f"theme:{ctx.kdc_class}"
        if theme_id not in kg.graph:
            kg.add_node(theme_id, node_type="Theme", label=ctx.kdc_class)
        kg.add_edge(book_id, theme_id, relation="EXPLORES")
