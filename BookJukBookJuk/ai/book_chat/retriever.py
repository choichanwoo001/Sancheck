"""Graph + Vector 하이브리드 리트리버.

질문에서 엔티티를 추출하고 두 소스를 병합해 RetrievedContext 를 반환한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from openai import AsyncOpenAI

from .graph_builder import KnowledgeGraph
from .vector_store import VectorStore, SearchResult


@dataclass
class RetrievedContext:
    graph_facts: list[str] = field(default_factory=list)
    vector_chunks: list[SearchResult] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        """검색 결과를 프롬프트에 주입할 문자열로 변환한다."""
        parts: list[str] = []

        if self.graph_facts:
            parts.append("### 관련 팩트 (지식 그래프에서 추출)")
            for fact in self.graph_facts[:20]:
                parts.append(f"  - {fact}")

        if self.vector_chunks:
            parts.append("\n### 관련 문서 (의미 검색 결과)")
            for r in self.vector_chunks:
                src_tag = f"[{r.chunk.source} / {r.chunk.doc_type}]"
                section = r.chunk.metadata.get("section_title", "")
                if section:
                    src_tag += f" ({section})"
                parts.append(f"{src_tag}\n{r.chunk.text}")

        return "\n".join(parts) if parts else "(검색 결과 없음)"

    def is_empty(self) -> bool:
        return not self.graph_facts and not self.vector_chunks


class HybridRetriever:
    def __init__(
        self,
        kg: KnowledgeGraph,
        vs: VectorStore,
        openai_client: AsyncOpenAI,
        graph_hops: int = 2,
        vector_top_k: int = 5,
    ) -> None:
        self.kg = kg
        self.vs = vs
        self.client = openai_client
        self.graph_hops = graph_hops
        self.vector_top_k = vector_top_k

    async def retrieve(self, query: str) -> RetrievedContext:
        """질문에 대해 그래프 팩트와 벡터 청크를 동시에 검색해 병합한다."""
        # 1) 그래프: 매칭 노드 → 팩트 추출
        matched_nodes = self.kg.find_matching_nodes(query)
        graph_facts: list[str] = []
        for node_id in matched_nodes[:5]:
            facts = self.kg.get_facts(node_id, hops=self.graph_hops)
            graph_facts.extend(facts)
        # 중복 제거 (순서 유지)
        seen: set[str] = set()
        unique_facts: list[str] = []
        for f in graph_facts:
            if f not in seen:
                seen.add(f)
                unique_facts.append(f)

        # 2) 벡터: 코사인 유사도 검색
        vector_results = await self.vs.search(self.client, query, top_k=self.vector_top_k)

        return RetrievedContext(graph_facts=unique_facts, vector_chunks=vector_results)
