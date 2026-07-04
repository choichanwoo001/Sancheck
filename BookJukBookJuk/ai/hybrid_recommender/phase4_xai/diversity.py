"""다양성 보정: MMR + Epsilon-greedy (요구사항 5)

필터 버블 파괴 전략:
1. MMR (Maximal Marginal Relevance):
   MMR_Score = λ · Relevance(i) - (1-λ) · max_{j∈S} Sim(i, j)
   관련성을 유지하면서 이미 선택된 아이템과의 유사도를 패널티로 부여

2. Epsilon-greedy (탐색-활용 균형):
   ε 확률로 랜덤 탐색 (exploitation) / (1-ε) 확률로 최고 점수 선택 (exploration)
   → 익숙한 장르에만 갇히지 않고 새로운 영역을 탐험
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ..phase3_scoring.hybrid_scorer import ScoredBook


class MMRReranker:
    """MMR (Maximal Marginal Relevance) 기반 다양성 재순위화.

    Carbonell & Goldstein (1998) 논문 기반 구현.

    Args:
        lambda_mmr: 관련성과 다양성의 균형 계수.
                    1.0 = 완전 관련성 우선, 0.0 = 완전 다양성 우선
                    (기본 0.6 권장)
    """

    def __init__(self, lambda_mmr: float = 0.6) -> None:
        if not 0.0 <= lambda_mmr <= 1.0:
            raise ValueError(f"lambda_mmr 은 0~1 범위여야 합니다: {lambda_mmr}")
        self.lambda_mmr = lambda_mmr

    def _cosine_sim(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """정규화된 벡터 간 코사인 유사도."""
        dot = float(np.dot(v1, v2))
        norm1 = float(np.linalg.norm(v1))
        norm2 = float(np.linalg.norm(v2))
        if norm1 < 1e-9 or norm2 < 1e-9:
            return 0.0
        return dot / (norm1 * norm2)

    def _max_sim_to_selected(
        self,
        candidate_vec: np.ndarray,
        selected: list["ScoredBook"],
    ) -> float:
        """선택된 항목들과의 최대 유사도를 계산한다."""
        if not selected:
            return 0.0
        sims = [
            self._cosine_sim(candidate_vec, s.vector)
            for s in selected
            if s.vector is not None
        ]
        return max(sims) if sims else 0.0

    def rerank(
        self,
        candidates: list["ScoredBook"],
        top_k: int,
    ) -> list["ScoredBook"]:
        """MMR 알고리즘으로 재순위화한다.

        Args:
            candidates: final_score 내림차순 정렬된 후보 목록
            top_k: 반환할 최종 추천 수

        Returns:
            다양성이 보정된 ScoredBook 목록
        """
        if not candidates:
            return []

        remaining = list(candidates)
        selected: list["ScoredBook"] = []

        while remaining and len(selected) < top_k:
            best_item = None
            best_mmr = float("-inf")

            for item in remaining:
                relevance = item.final_score

                if item.vector is not None:
                    max_sim = self._max_sim_to_selected(item.vector, selected)
                else:
                    # 벡터 없을 때: KDC 분류 기반 다양성 (간단한 휴리스틱)
                    same_kdc_count = sum(
                        1 for s in selected
                        if s.kdc_class and item.kdc_class and
                        s.kdc_class[:1] == item.kdc_class[:1]  # KDC 대분류 비교
                    )
                    max_sim = min(1.0, same_kdc_count * 0.3)

                mmr_score = (
                    self.lambda_mmr * relevance
                    - (1.0 - self.lambda_mmr) * max_sim
                )

                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_item = item

            if best_item is None:
                break

            selected.append(best_item)
            remaining.remove(best_item)

        return selected


class EpsilonGreedyExplorer:
    """Epsilon-greedy 탐색-활용 균형 전략.

    ε 확률로 예상치 못한 장르/주제의 책을 추천해
    사용자가 새로운 영역을 발견하도록 돕는다.

    Args:
        epsilon: 탐색 확률 (기본 0.15 = 15% 확률로 랜덤 탐색)
        seed: 재현 가능성을 위한 random seed
    """

    def __init__(self, epsilon: float = 0.15, seed: int | None = None) -> None:
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError(f"epsilon 은 0~1 범위여야 합니다: {epsilon}")
        self.epsilon = epsilon
        self._rng = random.Random(seed)

    def explore(
        self,
        top_candidates: list["ScoredBook"],
        exploration_pool: list["ScoredBook"],
        top_k: int,
    ) -> list["ScoredBook"]:
        """ε-greedy 로 최종 추천 목록을 구성한다.

        Args:
            top_candidates: 높은 점수 후보 (활용, exploitation)
            exploration_pool: 낮은 점수지만 다양한 후보 (탐색, exploration)
            top_k: 최종 추천 수

        Returns:
            활용 + 탐색이 섞인 추천 목록
        """
        n_explore = max(0, round(top_k * self.epsilon))
        n_exploit = top_k - n_explore

        # 활용: 상위 n_exploit 개
        exploit_results = top_candidates[:n_exploit]

        # 탐색: exploration_pool 에서 이미 선택된 것 제외 후 랜덤
        selected_isbns = {b.isbn13 for b in exploit_results}
        explore_pool = [
            b for b in exploration_pool
            if b.isbn13 not in selected_isbns
        ]

        if explore_pool and n_explore > 0:
            explore_sample = self._rng.sample(
                explore_pool, min(n_explore, len(explore_pool))
            )
        else:
            explore_sample = []

        return exploit_results + explore_sample

    def should_explore(self) -> bool:
        """현재 스텝에서 탐색 여부를 결정한다."""
        return self._rng.random() < self.epsilon


# ── 통합 후처리기 ─────────────────────────────────────────────────────────────


class DiversityPostProcessor:
    """MMR + Epsilon-greedy 를 결합한 다양성 후처리기.

    처리 흐름:
    1. HybridScorer 결과 (final_score 정렬된 후보들)를 입력받는다.
    2. MMR 으로 유사한 책들을 걸러내며 top-K 를 재선택한다.
    3. Epsilon-greedy 로 탐색 책을 일부 주입한다.
    """

    def __init__(
        self,
        mmr_lambda: float = 0.6,
        epsilon: float = 0.15,
        seed: int | None = None,
    ) -> None:
        self.mmr = MMRReranker(lambda_mmr=mmr_lambda)
        self.explorer = EpsilonGreedyExplorer(epsilon=epsilon, seed=seed)

    def process(
        self,
        candidates: list["ScoredBook"],
        top_k: int = 10,
    ) -> list["ScoredBook"]:
        """다양성 보정된 최종 추천 목록을 반환한다.

        Args:
            candidates: HybridScorer 에서 나온 final_score 정렬 후보
            top_k: 최종 추천 수

        Returns:
            다양성이 보정된 상위 top_k 개 ScoredBook
        """
        if not candidates:
            return []

        # 1) MMR 로 재순위화: 더 많은 후보에서 top_k * 2 개 선정
        mmr_pool_size = min(len(candidates), top_k * 3)
        mmr_results = self.mmr.rerank(candidates[:mmr_pool_size], top_k=top_k)

        # 2) Epsilon-greedy 탐색: MMR 결과에서 n_exploit, 나머지 후보에서 탐색
        mmr_selected_isbns = {b.isbn13 for b in mmr_results}
        exploration_pool = [b for b in candidates if b.isbn13 not in mmr_selected_isbns]

        final = self.explorer.explore(
            top_candidates=mmr_results,
            exploration_pool=exploration_pool,
            top_k=top_k,
        )

        return final

    def update_epsilon(self, new_epsilon: float) -> None:
        """사용자 피드백에 따라 탐색률을 동적으로 조정한다."""
        self.explorer.epsilon = max(0.0, min(1.0, new_epsilon))

    def update_mmr_lambda(self, new_lambda: float) -> None:
        """관련성-다양성 균형을 동적으로 조정한다."""
        self.mmr.lambda_mmr = max(0.0, min(1.0, new_lambda))
