"""Confidence Score 기반 KG 노이즈 필터링 (요구사항 2)

추출된 트리플에 복합 신뢰도를 부여하고 임계값 이하 엣지를 제거해
지식 그래프 오염을 방지한다.

복합 신뢰도 = LLM confidence × 소스 신뢰도 가중치 × 관계 유형 가중치
"""
from __future__ import annotations

from dataclasses import dataclass

from .entity_extractor import KGTriple

# ── 소스별 신뢰도 가중치 ──────────────────────────────────────────────────────
# 출처가 명확할수록 높은 가중치를 부여한다

SOURCE_WEIGHTS: dict[str, float] = {
    "위키피디아": 0.95,
    "wikipedia": 0.95,
    "알라딘": 0.85,
    "정보나루": 0.90,
    "추론": 0.60,
    "llm": 0.65,
    "unknown": 0.50,
}

# ── 관계 유형별 신뢰도 가중치 ─────────────────────────────────────────────────
# 팩트 기반 관계는 높고, 의미적 유사성 관계는 낮다

RELATION_WEIGHTS: dict[str, float] = {
    "WRITTEN_BY": 1.0,
    "PUBLISHED_BY": 1.0,
    "AWARDED": 0.95,
    "PART_OF_SERIES": 0.95,
    "HAS_CHARACTER": 0.85,
    "SET_IN": 0.85,
    "EXPLORES": 0.80,
    "INFLUENCED_BY": 0.75,
    "SIMILAR_TO": 0.65,
    "RELATED_TO": 0.55,
}

DEFAULT_RELATION_WEIGHT = 0.70


@dataclass
class FilterResult:
    passed: list[KGTriple]
    rejected: list[KGTriple]

    @property
    def pass_rate(self) -> float:
        total = len(self.passed) + len(self.rejected)
        return len(self.passed) / total if total > 0 else 0.0


class NoiseFilter:
    """복합 신뢰도 기반 KG 노이즈 필터."""

    def __init__(
        self,
        threshold: float = 0.50,
        source_weights: dict[str, float] | None = None,
        relation_weights: dict[str, float] | None = None,
    ) -> None:
        """
        Args:
            threshold: 최소 복합 신뢰도 (기본 0.50).
                       이 값 미만의 엣지는 제거된다.
            source_weights: 소스 신뢰도 가중치 커스터마이징.
            relation_weights: 관계 유형별 가중치 커스터마이징.
        """
        self.threshold = threshold
        self._source_weights = {**SOURCE_WEIGHTS, **(source_weights or {})}
        self._relation_weights = {**RELATION_WEIGHTS, **(relation_weights or {})}

    def compute_composite_confidence(self, triple: KGTriple) -> float:
        """LLM confidence × 소스 가중치 × 관계 가중치의 기하 평균."""
        llm_conf = triple.confidence
        src_key = triple.source.lower() if triple.source else "unknown"
        source_w = self._source_weights.get(triple.source, 
                   self._source_weights.get(src_key, 0.50))
        relation_w = self._relation_weights.get(
            triple.relation, DEFAULT_RELATION_WEIGHT
        )

        # 기하 평균: 어느 하나가 낮으면 전체 신뢰도가 크게 낮아진다
        composite = (llm_conf * source_w * relation_w) ** (1.0 / 3.0)
        return round(composite, 4)

    def filter_triples(
        self,
        triples: list[KGTriple],
        verbose: bool = False,
    ) -> list[KGTriple]:
        """임계값 미만의 트리플을 제거하고 통과된 목록만 반환한다."""
        result = self.filter_with_report(triples)
        if verbose:
            print(
                f"[NoiseFilter] 통과: {len(result.passed)}개 / "
                f"제거: {len(result.rejected)}개 "
                f"(통과율 {result.pass_rate:.1%})"
            )
        return result.passed

    def filter_with_report(
        self,
        triples: list[KGTriple],
    ) -> FilterResult:
        """필터링 결과를 통과/제거 목록과 함께 반환한다."""
        passed: list[KGTriple] = []
        rejected: list[KGTriple] = []

        for triple in triples:
            composite = self.compute_composite_confidence(triple)
            # 복합 신뢰도를 트리플에 반영
            triple.confidence = composite

            if composite >= self.threshold:
                passed.append(triple)
            else:
                rejected.append(triple)

        return FilterResult(passed=passed, rejected=rejected)

    def adjust_threshold(self, new_threshold: float) -> None:
        """런타임에 임계값을 동적으로 조정한다."""
        if not 0.0 <= new_threshold <= 1.0:
            raise ValueError(f"threshold 는 0~1 사이여야 합니다: {new_threshold}")
        self.threshold = new_threshold

    def stats(self, triples: list[KGTriple]) -> dict[str, float]:
        """트리플 집합의 신뢰도 통계를 반환한다."""
        if not triples:
            return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0}
        confs = [self.compute_composite_confidence(t) for t in triples]
        return {
            "count": len(confs),
            "mean": sum(confs) / len(confs),
            "min": min(confs),
            "max": max(confs),
        }
