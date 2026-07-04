"""LLM Function Calling 을 이용한 자동 엔티티/트리플 추출 (요구사항 1)

신간이 추가될 때마다 수동 작업 없이 BookContext 텍스트에서
엔티티(Entity)와 관계(Relation)를 추출해 KGStore 에 저장한다.
"""
from __future__ import annotations

import json
import sys
import os
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from book_chat.data_collector import BookContext

# ── OpenAI Function Calling 스키마 ────────────────────────────────────────────

_EXTRACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_kg_triples",
        "description": (
            "도서 텍스트에서 지식 그래프(KG) 엔티티와 관계 트리플을 추출합니다. "
            "각 트리플에는 신뢰도(confidence)를 0~1 사이 값으로 부여하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "description": "추출된 엔티티 목록",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "유일한 엔티티 ID (예: 'author:한강', 'theme:페미니즘')",
                            },
                            "type": {
                                "type": "string",
                                "enum": [
                                    "Book", "Author", "Character", "Theme",
                                    "Genre", "HistoricalPeriod", "Concept",
                                    "Award", "Publisher", "Series", "Nationality",
                                ],
                            },
                            "label": {"type": "string", "description": "표시용 이름"},
                            "description": {
                                "type": "string",
                                "description": "간단한 설명 (50자 이내)",
                            },
                        },
                        "required": ["id", "type", "label"],
                    },
                },
                "triples": {
                    "type": "array",
                    "description": "추출된 관계 트리플 목록",
                    "items": {
                        "type": "object",
                        "properties": {
                            "head": {"type": "string", "description": "head 엔티티 ID"},
                            "relation": {
                                "type": "string",
                                "description": (
                                    "관계 유형 (예: WRITTEN_BY, EXPLORES, SET_IN, "
                                    "HAS_CHARACTER, INFLUENCED_BY, AWARDED, "
                                    "SIMILAR_TO, PUBLISHED_BY, PART_OF_SERIES)"
                                ),
                            },
                            "tail": {"type": "string", "description": "tail 엔티티 ID"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                                "description": "관계 신뢰도 (0=불확실, 1=확실)",
                            },
                            "source": {
                                "type": "string",
                                "description": "출처 (위키피디아/알라딘/정보나루/추론)",
                            },
                        },
                        "required": ["head", "relation", "tail", "confidence"],
                    },
                },
            },
            "required": ["entities", "triples"],
        },
    },
}

# ── 데이터클래스 ──────────────────────────────────────────────────────────────

VALID_ENTITY_TYPES = {
    "Book", "Author", "Character", "Theme", "Genre",
    "HistoricalPeriod", "Concept", "Award", "Publisher", "Series", "Nationality",
}

MAX_ENTITY_LABEL_LEN = 40
MAX_ENTITY_DESC_LEN = 80
MAX_CONCEPT_ENTITIES = 12

ENTITY_ID_PREFIX_BY_TYPE: dict[str, str] = {
    "Book": "book:",
    "Author": "author:",
    "Character": "character:",
    "Theme": "theme:",
    "Genre": "genre:",
    "HistoricalPeriod": "period:",
    "Concept": "concept:",
    "Award": "award:",
    "Publisher": "publisher:",
    "Series": "series:",
    "Nationality": "nationality:",
}


def _normalize_compact(text: str) -> str:
    """노드 라벨/ID에 쓰일 짧은 명사구로 정규화한다."""
    t = (text or "").strip()
    # 줄바꿈/탭 제거, 과도한 공백 정리
    t = " ".join(t.replace("\t", " ").replace("\n", " ").split())
    # 따옴표류 제거
    t = t.strip(" \"'“”‘’")
    return t


def _looks_like_sentence(label: str) -> bool:
    """문장형 라벨(길고 구두점 많은 형태)을 대략 판별한다."""
    s = _normalize_compact(label)
    if len(s) > MAX_ENTITY_LABEL_LEN:
        return True
    if any(p in s for p in (".", "?", "!", "…")):
        return True
    # 조사/서술이 섞인 긴 구절은 KG 엔티티로 부적합한 경우가 많다
    if ("다" in s[-2:]) and len(s) > 18:
        return True
    return False


def _coerce_entity_id(entity_type: str, raw_id: str, label: str) -> str:
    prefix = ENTITY_ID_PREFIX_BY_TYPE.get(entity_type, "concept:")
    rid = _normalize_compact(raw_id)
    if rid.startswith(prefix) and len(rid) > len(prefix):
        return rid
    # prefix가 없거나 잘못된 경우: label 기반으로 재생성
    base = _normalize_compact(label) or rid
    return f"{prefix}{base}" if base else f"{prefix}unknown"


@dataclass
class KGEntity:
    id: str
    type: str
    label: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in VALID_ENTITY_TYPES:
            self.type = "Concept"


@dataclass
class KGTriple:
    head: str
    relation: str
    tail: str
    confidence: float
    source: str = "추론"

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, self.confidence))


# ── EntityExtractor ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """당신은 도서 지식 그래프 전문가입니다.
주어진 도서 정보 텍스트를 분석하여 엔티티와 관계 트리플을 추출하세요.

추출 기준:
- 엔티티 label 은 반드시 2~20자 내외의 "짧은 명사구"만 사용하세요. 문장/요약/설명문을 엔티티로 만들지 마세요.
- 엔티티는 정규화된 타입/ID 규칙을 지키세요. (author:, theme:, genre:, publisher:, award:, series:, concept:, period:, character:, nationality:, book:)
- 명확하게 언급된 관계만 높은 신뢰도(0.8~1.0)로 추출하세요
- 텍스트에서 암시되는 관계는 중간 신뢰도(0.5~0.7)로 표시하세요
- 추측에 불과한 관계는 낮은 신뢰도(0.3~0.4)로 표시하거나 제외하세요
- 도서의 book_id 는 항상 'book:{isbn_or_title}' 형태를 사용하세요
- 저자 ID 는 'author:{이름}', 테마는 'theme:{주제}' 형태를 사용하세요"""


class EntityExtractor:
    """LLM Function Calling 기반 자동 엔티티/트리플 추출기."""

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.client = openai_client
        self.model = model

    def _build_input_text(self, ctx: BookContext) -> str:
        """BookContext 에서 추출용 텍스트를 조합한다."""
        parts: list[str] = []

        book_id = ctx.isbn13 or ctx.title
        parts.append(f"[도서 ID] book:{book_id}")
        parts.append(f"[제목] {ctx.title}")
        if ctx.authors:
            parts.append(f"[저자] {ctx.authors}")
        if ctx.publisher:
            parts.append(f"[출판사] {ctx.publisher}")
        if ctx.published_year:
            parts.append(f"[출판연도] {ctx.published_year}")
        if ctx.kdc_class:
            parts.append(f"[KDC 분류] {ctx.kdc_class}")
        if ctx.description:
            parts.append(f"[책 소개]\n{ctx.description[:800]}")
        if ctx.author_bio:
            parts.append(f"[저자 소개]\n{ctx.author_bio[:400]}")
        if ctx.wiki_book_summary:
            parts.append(f"[Wikipedia 도서 요약]\n{ctx.wiki_book_summary[:600]}")
        if ctx.wiki_author_summary:
            parts.append(f"[Wikipedia 저자 정보]\n{ctx.wiki_author_summary[:400]}")
        if ctx.keywords:
            kw_text = ", ".join(f"{kw.word}({kw.weight:.2f})" for kw in ctx.keywords[:15])
            parts.append(f"[핵심 키워드] {kw_text}")
        for sec in ctx.wiki_extra_sections[:4]:
            parts.append(f"[섹션: {sec['title']}]\n{sec['text'][:300]}")

        return "\n\n".join(parts)

    async def extract(
        self,
        ctx: BookContext,
    ) -> tuple[list[KGEntity], list[KGTriple]]:
        """BookContext 에서 엔티티와 트리플을 추출한다."""
        input_text = self._build_input_text(ctx)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": input_text},
                ],
                tools=[_EXTRACTION_TOOL],
                tool_choice={"type": "function", "function": {"name": "extract_kg_triples"}},
                temperature=0.1,
            )

            tool_call = response.choices[0].message.tool_calls[0]
            raw = json.loads(tool_call.function.arguments)

        except Exception as e:
            print(f"[WARN] LLM 엔티티 추출 실패 ({ctx.title}): {e}")
            return self._fallback_extract(ctx)

        raw_entities = raw.get("entities", []) or []
        entities: list[KGEntity] = []

        # 항상 book 노드는 포함 (LLM 출력이 이상해도 KG가 끊기지 않게)
        book_key = ctx.isbn13 or ctx.title
        book_id = f"book:{book_key}"
        entities.append(KGEntity(
            id=book_id,
            type="Book",
            label=_normalize_compact(ctx.title)[:MAX_ENTITY_LABEL_LEN] or book_key,
            description=_normalize_compact(ctx.description)[:MAX_ENTITY_DESC_LEN],
        ))

        for e in raw_entities:
            if not isinstance(e, dict):
                continue
            etype = str(e.get("type") or "Concept")
            label = _normalize_compact(str(e.get("label") or ""))
            if not label:
                continue
            if etype not in VALID_ENTITY_TYPES:
                etype = "Concept"
            # 문장형/긴 라벨은 KG 엔티티로 저장하지 않는다 (긴 텍스트는 임베딩 역할)
            if _looks_like_sentence(label):
                continue

            eid = _coerce_entity_id(etype, str(e.get("id") or ""), label)
            desc = _normalize_compact(str(e.get("description") or ""))[:MAX_ENTITY_DESC_LEN]
            entities.append(KGEntity(
                id=eid,
                type=etype,
                label=label[:MAX_ENTITY_LABEL_LEN],
                description=desc,
            ))

        # Concept 과다 생성 방지: 상한 적용 (나머지는 임베딩으로 흡수)
        concepts = [x for x in entities if x.type == "Concept"]
        if len(concepts) > MAX_CONCEPT_ENTITIES:
            kept: list[KGEntity] = []
            concept_kept = 0
            for x in entities:
                if x.type != "Concept":
                    kept.append(x)
                    continue
                if concept_kept < MAX_CONCEPT_ENTITIES:
                    kept.append(x)
                    concept_kept += 1
            entities = kept

        # 중복 ID 제거 (첫 항목 우선)
        seen_ids: set[str] = set()
        deduped: list[KGEntity] = []
        for ent in entities:
            if ent.id in seen_ids:
                continue
            seen_ids.add(ent.id)
            deduped.append(ent)
        entities = deduped

        triples = [
            KGTriple(
                head=t.get("head", ""),
                relation=t.get("relation", "RELATED_TO"),
                tail=t.get("tail", ""),
                confidence=float(t.get("confidence", 0.5)),
                source=t.get("source", "추론"),
            )
            for t in raw.get("triples", [])
            if t.get("head") and t.get("tail")
        ]

        # 저장될 엔티티 집합에 포함되는 트리플만 남긴다 (유령 노드 방지)
        valid_entity_ids = {e.id for e in entities}
        triples = [
            tr for tr in triples
            if tr.head in valid_entity_ids and tr.tail in valid_entity_ids
        ]

        print(f"[INFO] '{ctx.title}' 추출 완료: 엔티티 {len(entities)}개, 트리플 {len(triples)}개")
        return entities, triples

    def _fallback_extract(
        self,
        ctx: BookContext,
    ) -> tuple[list[KGEntity], list[KGTriple]]:
        """LLM 실패 시 규칙 기반 폴백 추출."""
        import re

        book_id = f"book:{ctx.isbn13 or ctx.title}"
        entities: list[KGEntity] = [
            KGEntity(id=book_id, type="Book", label=ctx.title, description=ctx.description[:200])
        ]
        triples: list[KGTriple] = []

        # 저자 추출
        if ctx.authors:
            author_names = re.split(r"[,;|]", ctx.authors)
            for raw_name in author_names:
                name = re.sub(r"\(.*?\)|（.*?）", "", raw_name).strip()
                name = re.sub(r"^[^:：]+[:：]\s*", "", name).strip()
                if name and len(name) > 1:
                    author_id = f"author:{name}"
                    entities.append(KGEntity(id=author_id, type="Author", label=name))
                    triples.append(KGTriple(
                        head=book_id, relation="WRITTEN_BY",
                        tail=author_id, confidence=1.0, source="알라딘",
                    ))

        # 출판사
        if ctx.publisher:
            pub_id = f"publisher:{ctx.publisher}"
            entities.append(KGEntity(id=pub_id, type="Publisher", label=ctx.publisher))
            triples.append(KGTriple(
                head=book_id, relation="PUBLISHED_BY",
                tail=pub_id, confidence=1.0, source="알라딘",
            ))

        # KDC 분류
        if ctx.kdc_class:
            theme_id = f"theme:{ctx.kdc_class}"
            entities.append(KGEntity(id=theme_id, type="Theme", label=ctx.kdc_class))
            triples.append(KGTriple(
                head=book_id, relation="EXPLORES",
                tail=theme_id, confidence=0.9, source="정보나루",
            ))

        # 키워드
        for kw in ctx.keywords[:10]:
            concept_id = f"concept:{kw.word}"
            entities.append(KGEntity(id=concept_id, type="Concept", label=kw.word))
            triples.append(KGTriple(
                head=book_id, relation="EXPLORES",
                tail=concept_id, confidence=min(kw.weight, 1.0), source="정보나루",
            ))

        return entities, triples

    async def extract_and_store(
        self,
        ctx: BookContext,
        kg_store: "KGStore",  # type: ignore[name-defined]
        noise_filter: "NoiseFilter | None" = None,  # type: ignore[name-defined]
    ) -> None:
        """추출 후 즉시 KGStore 에 저장. 신간 자동 처리용."""
        from .kg_store import KGStore
        from .noise_filter import NoiseFilter

        entities, triples = await self.extract(ctx)

        if noise_filter:
            triples = noise_filter.filter_triples(triples)

        # 엔티티 저장
        for entity in entities:
            kg_store.add_node(
                node_id=entity.id,
                node_type=entity.type,
                label=entity.label,
                description=entity.description,
                **entity.metadata,
            )

        # 트리플 저장
        for triple in triples:
            kg_store.add_edge(
                src=triple.head,
                dst=triple.tail,
                relation=triple.relation,
                confidence=triple.confidence,
                source=triple.source,
            )

        print(f"[INFO] '{ctx.title}' KG 저장 완료: "
              f"엔티티 {len(entities)}개, 트리플 {len(triples)}개")
