"""하이브리드 스코어링 엔진

Final_Score = α × Graph_Score + (1-α) × Vector_Score

α (alpha) 는 사용자 프로파일 풍부도에 따라 동적으로 결정된다:
- 프로파일 풍부 (많은 이력) → α 증가 → KG 그래프 점수 비중 높음
- 콜드스타트 사용자 (이력 없음) → α 감소 → 벡터 유사도 의존

후보 책 수집 전략 (`_collect_candidates`):
1. Vector Store: 시드 가중 평균 쿼리 벡터로 유사 도서 top-N
2. KG 리플: Seed의 `book:isbn`에서 hop 확산해 Book 타입 노드 ISBN 추가
3. 후보가 10개 미만이면 KG에 등록된 모든 Book ISBN을 폴백으로 추가
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import numpy as np

from .user_profile import UserProfile

if TYPE_CHECKING:
    from ..phase1_kg.kg_store import NetworkXKGStore
    from ..phase2_model.ripplenet import RippleNetScorer
    from ..phase2_model.vector_store import BookVectorStore


@dataclass
class ScoredBook:
    """점수가 매겨진 추천 후보 도서."""
    isbn13: str
    title: str
    authors: str
    graph_score: float       # RippleNet / KG 확산 점수 (0~1)
    vector_score: float      # 벡터 유사도 점수 (0~1)
    final_score: float       # α·graph + (1-α)·vector
    alpha_used: float        # 실제 사용된 α 값
    kdc_class: str = ""
    publisher: str = ""
    published_year: str = ""
    vector: np.ndarray | None = None
    metadata: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"ScoredBook({self.title!r}, "
            f"final={self.final_score:.3f}, "
            f"graph={self.graph_score:.3f}, "
            f"vec={self.vector_score:.3f})"
        )


class HybridScorer:
    """하이브리드 추천 스코어링 엔진.

    Args:
        kg_store: NetworkX KG 저장소
        vector_store: 책 단위 벡터 DB
        ripplenet_scorer: KG Ripple 점수 계산기
        alpha_min: α 최솟값 (콜드스타트 사용자)
        alpha_max: α 최댓값 (프로파일 풍부 사용자)
        candidate_pool_size: 후보 도서 풀 크기
    """

    def __init__(
        self,
        kg_store: "NetworkXKGStore",
        vector_store: "BookVectorStore",
        ripplenet_scorer: "RippleNetScorer | None" = None,
        alpha_min: float = 0.1,
        alpha_max: float = 0.7,
        candidate_pool_size: int = 50,
    ) -> None:
        self.kg = kg_store
        self.vector_store = vector_store
        self.ripplenet = ripplenet_scorer
        self.alpha_min = alpha_min
        self.alpha_max = alpha_max
        self.candidate_pool_size = candidate_pool_size

    def compute_alpha(self, user_profile: UserProfile) -> float:
        """프로파일 풍부도에 따라 동적으로 α 를 계산한다.

        richness=0 → alpha_min (벡터 의존)
        richness=1 → alpha_max (그래프 의존)
        """
        richness = user_profile.richness
        return self.alpha_min + (self.alpha_max - self.alpha_min) * richness

    def _collect_candidates(
        self,
        user_profile: UserProfile,
        seed_weights: dict[str, float],
        user_query_vector: np.ndarray | None,
        exclude_isbns: list[str],
    ) -> tuple[set[str], dict[str, Any]]:
        """후보 도서 ISBN 집합을 수집한다. 두 번째 값은 진단용 메타데이터."""
        candidates: set[str] = set()
        exclude_set = set(exclude_isbns)
        diag: dict[str, Any] = {
            "vector_search_hits": 0,
            "ripple_book_added": 0,
            "fallback_book_added": 0,
            "query_vector_ok": user_query_vector is not None,
        }

        # 방법 1: 벡터 유사도 기반 후보
        if user_query_vector is not None:
            vec_results = self.vector_store.search(
                user_query_vector,
                top_k=self.candidate_pool_size,
                exclude_isbns=exclude_isbns,
            )
            diag["vector_search_hits"] = len(vec_results)
            for r in vec_results:
                candidates.add(r.book.isbn13)

        # 방법 2: KG 확산 기반 후보 (Book 타입 노드)
        before_ripple = len(candidates)
        seed_entity_ids = [f"book:{isbn}" for isbn in seed_weights.keys()]
        for hop in range(1, 3):
            ripple_set = self.kg.get_ripple_set(
                seed_entity_ids, hop=hop, n_memory=30
            )
            for head_id, rel, tail_id in ripple_set:
                # Book 타입 노드이면 후보로 추가
                node = self.kg.get_node(tail_id)
                if node and node.get("type") == "Book":
                    isbn = node.get("isbn13", "")
                    if not isbn:
                        # ID 에서 ISBN 추출 시도 (book:ISBN13 형태)
                        isbn = tail_id.replace("book:", "")
                    if isbn and isbn not in exclude_set:
                        candidates.add(isbn)
        diag["ripple_book_added"] = len(candidates) - before_ripple

        # 방법 3: KG 에서 모든 Book 노드를 폴백으로 추가 (후보가 부족할 때)
        before_fb = len(candidates)
        if len(candidates) < 10:
            all_books = self.kg.get_book_ids()
            for book_id in all_books:
                isbn = book_id.replace("book:", "")
                if isbn not in exclude_set:
                    candidates.add(isbn)
        diag["fallback_book_added"] = len(candidates) - before_fb

        book_ids = self.kg.get_book_ids()
        diag["kg_book_node_count"] = len(book_ids)
        diag["kg_book_isbns"] = {bid.replace("book:", "") for bid in book_ids}
        diag["exclude_count"] = len(exclude_set)

        return candidates, diag

    def _compute_vector_scores(
        self,
        candidate_isbns: list[str],
        user_query_vector: np.ndarray | None,
    ) -> dict[str, float]:
        """후보 도서들의 벡터 유사도 점수를 계산한다."""
        if user_query_vector is None:
            return {isbn: 0.0 for isbn in candidate_isbns}

        scores: dict[str, float] = {}
        q = user_query_vector / (np.linalg.norm(user_query_vector) + 1e-9)

        for isbn in candidate_isbns:
            vec = self.vector_store.get_vector(isbn)
            if vec is not None:
                cosine = float(np.dot(q, vec))
                scores[isbn] = max(0.0, cosine)
            else:
                scores[isbn] = 0.0

        return scores

    def _compute_graph_scores(
        self,
        candidate_isbns: list[str],
        seed_isbns: list[str],
        seed_weights: dict[str, float],
    ) -> dict[str, float]:
        """RippleNetScorer 또는 KG 구조 기반 그래프 점수를 계산한다."""
        if self.ripplenet is not None:
            return self.ripplenet.score(
                seed_isbns=seed_isbns,
                candidate_isbns=candidate_isbns,
                seed_weights=seed_weights,
            )

        # RippleNet 없을 때: KG 공유 이웃 유사도로 폴백
        scores: dict[str, float] = {}
        seed_entity_ids = {f"book:{isbn}" for isbn in seed_isbns}

        # 각 seed 의 이웃 집합
        seed_neighbor_sets: list[set[str]] = []
        for seed_id in seed_entity_ids:
            neighbors = {n for n, _, _ in self.kg.get_neighbors(seed_id)}
            seed_neighbor_sets.append(neighbors)

        all_seed_neighbors = set.union(*seed_neighbor_sets) if seed_neighbor_sets else set()

        for isbn in candidate_isbns:
            book_id = f"book:{isbn}"
            cand_neighbors = {n for n, _, _ in self.kg.get_neighbors(book_id)}

            if not all_seed_neighbors or not cand_neighbors:
                scores[isbn] = 0.0
            else:
                # Jaccard 유사도
                intersection = len(all_seed_neighbors & cand_neighbors)
                union = len(all_seed_neighbors | cand_neighbors)
                scores[isbn] = intersection / union if union > 0 else 0.0

        return scores

    def _build_user_query_vector(
        self,
        seed_weights: dict[str, float],
    ) -> np.ndarray | None:
        """시드 책들의 가중 평균 벡터로 사용자 쿼리 벡터를 생성한다."""
        vecs: list[np.ndarray] = []
        weights: list[float] = []

        for isbn, w in seed_weights.items():
            vec = self.vector_store.get_vector(isbn)
            if vec is not None:
                vecs.append(vec)
                weights.append(w)

        if not vecs:
            return None

        w_arr = np.array(weights, dtype=np.float32)
        w_arr /= w_arr.sum()
        user_vec = sum(wi * vi for wi, vi in zip(w_arr, vecs))
        norm = np.linalg.norm(user_vec)
        return user_vec / norm if norm > 0 else user_vec

    def score_candidates(
        self,
        user_profile: UserProfile,
        reference_time: datetime | None = None,
        n_results: int = 20,
        verbose: bool = False,
    ) -> list[ScoredBook]:
        """하이브리드 점수로 추천 후보 도서를 랭킹한다.

        Args:
            user_profile: 사용자 행동 이력
            reference_time: 기준 시각 (시간 감쇠 계산용)
            n_results: 반환할 후보 수
            verbose: True면 후보 수집·부재 원인을 표준 출력에 상세 기록

        Returns:
            final_score 내림차순으로 정렬된 ScoredBook 목록
        """
        ref = reference_time or datetime.now(timezone.utc)

        # 1) 시간 감쇠 적용 seed 가중치
        seed_weights = user_profile.get_weighted_seeds(reference_time=ref)
        seed_isbns = list(seed_weights.keys())
        exclude_isbns = seed_isbns  # 이미 읽은 책은 제외

        if not seed_isbns:
            # 완전 콜드스타트: 전체 책에서 인기도 기반 폴백
            print("          [요약] 시드 ISBN 없음 → 콜드스타트 분기")
            out = self._cold_start_recommend(n_results)
            if not out and len(self.vector_store) == 0:
                print(
                    "          [원인] 콜드스타트인데 벡터 스토어도 비어 있어 추천할 책이 없습니다."
                )
            return out

        # 2) 동적 alpha 결정
        alpha = self.compute_alpha(user_profile)

        # 3) 사용자 쿼리 벡터 생성
        user_query_vec = self._build_user_query_vector(seed_weights)
        seeds_with_vec = sum(
            1 for isbn in seed_weights if self.vector_store.get_vector(isbn) is not None
        )

        # 4) 후보 수집
        raw_candidates, cand_diag = self._collect_candidates(
            user_profile, seed_weights, user_query_vec, exclude_isbns
        )
        candidate_isbns = list(raw_candidates)

        print(
            f"          [요약] 벡터 스토어 {len(self.vector_store)}권 | "
            f"시드 ISBN {len(seed_isbns)}개(임베딩 있는 시드 {seeds_with_vec}개) | "
            f"쿼리 벡터 {'있음' if user_query_vec is not None else '없음'} | "
            f"수집된 후보 {len(candidate_isbns)}개 | KG Book 노드 {cand_diag['kg_book_node_count']}개"
        )
        if verbose:
            print(
                "          [진단] 후보 수집 상세: "
                f"벡터 검색 {cand_diag['vector_search_hits']}건, "
                f"KG 리플 {cand_diag['ripple_book_added']}건, "
                f"폴백 추가 {cand_diag['fallback_book_added']}건"
            )

        if not candidate_isbns:
            kg_isbns = cand_diag.get("kg_book_isbns") or set()
            non_seed_in_kg = kg_isbns - set(seed_isbns)
            lines = [
                "          [원인] 추천 후보가 0개입니다.",
                "            · 이력에 있는 ISBN은 후보에서 제외됩니다.",
            ]
            if len(self.vector_store) == 0:
                lines.append(
                    "            · book_vectors(메모리)가 비어 있어 유사 도서 검색 경로가 없습니다. "
                    "`build_hybrid_catalog.py` 실행 시 HYBRID_PERSIST_EMBEDDINGS=1 로 저장됐는지 확인하세요."
                )
            if user_query_vec is None and seeds_with_vec == 0:
                lines.append(
                    "            · 시드 ISBN에 해당하는 임베딩이 없어 사용자 쿼리 벡터를 만들 수 없습니다."
                )
            if not non_seed_in_kg and kg_isbns:
                lines.append(
                    "            · KG에 있는 Book 노드가 모두 이미 읽은 책(시드)과 겹칩니다. "
                    "이력에 없는 다른 ISBN을 카탈로그에 넣어 KG/벡터를 넓히면 추천이 생깁니다."
                )
            elif not kg_isbns:
                lines.append(
                    "            · KG에 Book 타입 노드가 없습니다."
                )
            for line in lines:
                print(line)
            return []

        # 5) 점수 계산
        vector_scores = self._compute_vector_scores(candidate_isbns, user_query_vec)
        graph_scores = self._compute_graph_scores(candidate_isbns, seed_isbns, seed_weights)

        # 6) 하이브리드 최종 점수: Final = α·Graph + (1-α)·Vector
        scored_books: list[ScoredBook] = []
        for isbn in candidate_isbns:
            g_score = graph_scores.get(isbn, 0.0)
            v_score = vector_scores.get(isbn, 0.0)
            final = alpha * g_score + (1.0 - alpha) * v_score

            bv = self.vector_store.get_book(isbn)
            if bv:
                scored_books.append(ScoredBook(
                    isbn13=isbn,
                    title=bv.title,
                    authors=bv.authors,
                    graph_score=g_score,
                    vector_score=v_score,
                    final_score=final,
                    alpha_used=alpha,
                    kdc_class=bv.kdc_class,
                    publisher=bv.publisher,
                    published_year=bv.published_year,
                    vector=bv.vector,
                ))
            else:
                # BookVector 없는 경우 (KG 에만 있는 책)
                node = self.kg.get_node(f"book:{isbn}")
                if node:
                    scored_books.append(ScoredBook(
                        isbn13=isbn,
                        title=node.get("label", isbn),
                        authors="",
                        graph_score=g_score,
                        vector_score=v_score,
                        final_score=final,
                        alpha_used=alpha,
                    ))

        scored_books.sort(key=lambda x: x.final_score, reverse=True)
        out = scored_books[:n_results]
        if verbose and out:
            top = ", ".join(f"{b.isbn13}:{b.final_score:.3f}" for b in out[:5])
            print(f"          [진단] 상위 후보(최대 5개) final_score: {top}")
        return out

    def _cold_start_recommend(self, n_results: int) -> list[ScoredBook]:
        """시드 ISBN이 없을 때 벡터 스토어에 있는 도서를 순서대로 폴백 후보로 반환한다.

        점수는 플레이스홀더(그래프 0, 벡터·최종 0.5, alpha_used=0)이며 유사도 랭킹은 하지 않는다.
        """
        all_books = self.vector_store._books
        if not all_books:
            return []

        results: list[ScoredBook] = []
        for bv in all_books[:n_results]:
            results.append(ScoredBook(
                isbn13=bv.isbn13,
                title=bv.title,
                authors=bv.authors,
                graph_score=0.0,
                vector_score=0.5,
                final_score=0.5,
                alpha_used=0.0,
                kdc_class=bv.kdc_class,
                publisher=bv.publisher,
                published_year=bv.published_year,
                vector=bv.vector,
            ))
        return results
