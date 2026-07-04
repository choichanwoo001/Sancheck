"""북적북적 하이브리드 추천 엔진 - 통합 파이프라인

4단계 파이프라인을 하나의 클래스로 통합:
Phase 1: KG 자동 구축 (LLM 엔티티 추출 + 노이즈 필터링)
Phase 2: 임베딩 + RippleNet (콜드스타트 처리 + 벡터 저장)
Phase 3: 하이브리드 스코어링 (시간 감쇠 + α·Graph + (1-α)·Vector)
Phase 4: 다양성 보정 + XAI (MMR + ε-greedy + LLM 설명)
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from book_chat.data_collector import collect_book_context, BookContext

from .kg_supabase import load_kg_from_supabase, save_kg_to_supabase
from .vector_supabase import (
    load_book_vectors_from_supabase,
    upsert_all_book_vectors,
    upsert_book_vector,
)
from .supabase_book_context import (
    create_supabase_client_from_env,
    load_book_context_from_supabase,
)
from .phase1_kg.entity_extractor import EntityExtractor
from .phase1_kg.kg_store import NetworkXKGStore, create_kg_store
from .phase1_kg.noise_filter import NoiseFilter
from .phase2_model.cold_start import ColdStartEmbedder
from .phase2_model.ripplenet import RippleNetScorer
from .phase2_model.vector_store import BookVectorStore, BookVector
from .phase3_scoring.user_profile import UserProfile, UserAction, ActionType
from .phase3_scoring.hybrid_scorer import HybridScorer, ScoredBook
from .phase4_xai.diversity import DiversityPostProcessor
from .phase4_xai.explainer import RecommendationExplainer, ExplainedRecommendation


class HybridRecommenderPipeline:
    """북적북적 하이브리드 추천 엔진 파이프라인.

    사용 예시:
        pipeline = HybridRecommenderPipeline.from_env()

        # 책 등록
        await pipeline.add_book(isbn="9788937460470")

        # 사용자 이력 추가
        pipeline.user_profile.add_read("9788937460470", "채식주의자")

        # 추천 실행
        results = await pipeline.recommend(top_k=5)
        for r in results:
            print(r)

    Args:
        openai_client: AsyncOpenAI 클라이언트
        library_api_key: 정보나루 API 키
        aladin_api_key: 알라딘 TTB API 키
        noise_threshold: 노이즈 필터 임계값 (기본 0.50)
        mmr_lambda: MMR 다양성 계수 (기본 0.6)
        epsilon: Epsilon-greedy 탐색률 (기본 0.15)
        use_pinecone: Pinecone 벡터 DB 사용 여부
        pinecone_config: Pinecone 연결 설정 (선택적)
        supabase_client: Supabase 클라이언트 (선택, `use_supabase` 와 함께)
        use_supabase: True 이면 ISBN 등록 시 `books`+`book_api_cache` 우선 로드
        persist_kg: True 이면 KG를 `kg_nodes`/`kg_edges`에 저장·시작 시 로드 (`HYBRID_PERSIST_KG`)
        persist_embeddings: True 이면 `book_vectors`에 임베딩 upsert·시작 시 로드 (`HYBRID_PERSIST_EMBEDDINGS`, 기본은 persist_kg 와 동일)
    """

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        library_api_key: str = "",
        aladin_api_key: str = "",
        noise_threshold: float = 0.50,
        mmr_lambda: float = 0.6,
        epsilon: float = 0.15,
        use_pinecone: bool = False,
        pinecone_config: dict | None = None,
        user_id: str = "default_user",
        supabase_client: Any | None = None,
        use_supabase: bool = False,
        persist_kg: bool = False,
        persist_embeddings: bool = False,
    ) -> None:
        self.client = openai_client
        self.library_api_key = library_api_key
        self.aladin_api_key = aladin_api_key
        self.supabase_client = supabase_client
        self.use_supabase = bool(use_supabase and supabase_client is not None)
        self.persist_kg = bool(persist_kg and supabase_client is not None)
        self.persist_embeddings = bool(persist_embeddings and supabase_client is not None)

        # ── Phase 1: KG (인메모리 NetworkX; 영속은 Supabase) ────────────────
        self.kg: NetworkXKGStore = create_kg_store()
        if self.persist_kg:
            loaded = load_kg_from_supabase(supabase_client)
            if loaded is not None and loaded.node_count() > 0:
                self.kg = loaded
                print(f"[KG] Supabase에서 로드: {self.kg.summary()}")
        self.entity_extractor = EntityExtractor(openai_client)
        self.noise_filter = NoiseFilter(threshold=noise_threshold)

        # ── Phase 2: 임베딩 + 모델 ─────────────────────────────────────────
        self.cold_start = ColdStartEmbedder(openai_client)
        self.vector_store = BookVectorStore(
            use_pinecone=use_pinecone,
            pinecone_config=pinecone_config,
        )
        self._book_titles: dict[str, str] = {}
        if self.persist_embeddings:
            loaded_vec = load_book_vectors_from_supabase(supabase_client)
            if loaded_vec:
                for bv in loaded_vec:
                    self.vector_store.add(bv)
                    self._book_titles[bv.isbn13] = bv.title
                print(f"[Vector] Supabase에서 로드: {len(loaded_vec)}권")

        self.ripplenet_scorer: RippleNetScorer | None = None  # add_books 후 초기화

        # ── Phase 3: 스코어링 ──────────────────────────────────────────────
        self.user_profile = UserProfile(user_id=user_id)
        self.scorer: HybridScorer | None = None  # add_books 후 초기화

        # ── Phase 4: 다양성 + XAI ─────────────────────────────────────────
        self.diversity = DiversityPostProcessor(
            mmr_lambda=mmr_lambda,
            epsilon=epsilon,
        )
        self.explainer = RecommendationExplainer(openai_client, self.kg)

        if self.kg.node_count() > 0 or len(self.vector_store) > 0:
            self._update_ripplenet_scorer()

    @classmethod
    def from_env(cls, user_id: str = "default_user", **kwargs: Any) -> "HybridRecommenderPipeline":
        """환경 변수에서 설정을 읽어 파이프라인을 초기화한다.

        `HYBRID_USE_SUPABASE=1` 이고 `SUPABASE_URL` + 키가 있으면 DB에서 BookContext 로드.
        """
        from pathlib import Path

        from dotenv import load_dotenv

        _root = Path(__file__).resolve().parents[2]
        _env = _root / ".env"
        if _env.is_file():
            load_dotenv(_env)

        openai_key = os.getenv("OPENAI_API_KEY", "")
        if not openai_key:
            raise ValueError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")

        client = AsyncOpenAI(api_key=openai_key)

        use_supabase_kw = kwargs.pop("use_supabase", None)
        supabase_kw = kwargs.pop("supabase_client", None)
        if use_supabase_kw is None:
            use_supabase_kw = os.getenv("HYBRID_USE_SUPABASE", "").lower() in ("1", "true", "yes")
        persist_kg_kw = kwargs.pop("persist_kg", None)
        if persist_kg_kw is None:
            persist_kg_kw = os.getenv("HYBRID_PERSIST_KG", "").lower() in ("1", "true", "yes")

        persist_emb_kw = kwargs.pop("persist_embeddings", None)
        if persist_emb_kw is None:
            pe = os.getenv("HYBRID_PERSIST_EMBEDDINGS", "").strip().lower()
            if pe in ("0", "false", "no"):
                persist_emb_kw = False
            elif pe in ("1", "true", "yes"):
                persist_emb_kw = True
            else:
                persist_emb_kw = bool(persist_kg_kw)

        sb_client = supabase_kw
        if use_supabase_kw and sb_client is None:
            sb_client = create_supabase_client_from_env()
        if (persist_kg_kw or persist_emb_kw) and sb_client is None:
            sb_client = create_supabase_client_from_env()

        if use_supabase_kw and sb_client is None:
            print(
                "[WARN] HYBRID_USE_SUPABASE 이지만 SUPABASE_URL/KEY 가 없어 API 수집으로 진행합니다."
            )
        if persist_kg_kw and sb_client is None:
            print(
                "[WARN] HYBRID_PERSIST_KG 이지만 SUPABASE_URL/KEY 가 없어 KG DB 영속을 건너뜁니다."
            )
        if persist_emb_kw and sb_client is None:
            print(
                "[WARN] HYBRID_PERSIST_EMBEDDINGS 이지만 SUPABASE_URL/KEY 가 없어 임베딩 DB 동기화를 건너뜁니다."
            )

        return cls(
            openai_client=client,
            library_api_key=os.getenv("LIBRARY_API_KEY", ""),
            aladin_api_key=os.getenv("ALADIN_API_KEY", ""),
            user_id=user_id,
            supabase_client=sb_client,
            use_supabase=bool(use_supabase_kw and sb_client is not None),
            persist_kg=bool(persist_kg_kw and sb_client is not None),
            persist_embeddings=bool(persist_emb_kw and sb_client is not None),
            **kwargs,
        )

    # ── Phase 1+2: 책 등록 ───────────────────────────────────────────────────

    async def add_book(
        self,
        isbn: str | None = None,
        title: str | None = None,
        author: str | None = None,
        ctx: BookContext | None = None,
        _persist_db: bool = True,
    ) -> BookContext:
        """책을 시스템에 등록한다 (KG 구축 + 임베딩 저장).

        Args:
            isbn: ISBN-13 (알 경우)
            title: 책 제목 (ISBN 없을 때)
            author: 저자명 (선택)
            ctx: 이미 수집된 BookContext (API 호출 절약)

        Returns:
            수집된 BookContext
        """
        # 1) 데이터 수집 (Supabase 우선, 없으면 기존 API)
        if ctx is None:
            if (
                self.use_supabase
                and self.supabase_client
                and isbn
                and str(isbn).strip()
            ):
                isbn_key = str(isbn).strip()
                ctx = await asyncio.to_thread(
                    load_book_context_from_supabase,
                    self.supabase_client,
                    isbn_key,
                )
                if ctx is not None:
                    print(f"[Phase 1] 데이터 로드(Supabase): {isbn_key}")
            if ctx is None:
                print(f"[Phase 1] 데이터 수집(API): {isbn or title}")
                ctx = await collect_book_context(
                    isbn13=isbn,
                    title=title,
                    author=author,
                    library_api_key=self.library_api_key,
                    aladin_api_key=self.aladin_api_key,
                )

        print(f"[Phase 1] KG 구축: '{ctx.title}'")

        # 2) LLM 엔티티 추출 + KG 저장
        await self.entity_extractor.extract_and_store(
            ctx, self.kg, self.noise_filter
        )

        # 3) 책 임베딩 생성 + 벡터 저장
        print(f"[Phase 2] 임베딩 생성: '{ctx.title}'")
        vector, is_cold = await self.cold_start.get_book_vector(ctx)

        self.vector_store.add(BookVector(
            isbn13=ctx.isbn13 or ctx.title,
            title=ctx.title,
            authors=ctx.authors,
            vector=vector,
            kdc_class=ctx.kdc_class,
            publisher=ctx.publisher,
            published_year=ctx.published_year,
            is_cold_start=is_cold,
        ))

        isbn_key = ctx.isbn13 or ctx.title
        self._book_titles[isbn_key] = ctx.title

        # 4) RippleNet 스코어러 재초기화 (엔티티 벡터 업데이트)
        self._update_ripplenet_scorer()

        print(f"[OK] '{ctx.title}' 등록 완료 "
              f"({'콜드스타트' if is_cold else '일반'} 임베딩)")

        if _persist_db and self.persist_kg and self.supabase_client:
            await asyncio.to_thread(
                save_kg_to_supabase, self.supabase_client, self.kg
            )
        if _persist_db and self.persist_embeddings and self.supabase_client:
            bv = self.vector_store.get_book(isbn_key)
            if bv is not None:
                await asyncio.to_thread(
                    upsert_book_vector, self.supabase_client, bv
                )
        return ctx

    async def add_books(
        self,
        isbn_list: list[str] | None = None,
        title_author_list: list[tuple[str, str]] | None = None,
        concurrency: int = 3,
    ) -> list[BookContext]:
        """여러 책을 병렬로 등록한다.

        Args:
            isbn_list: ISBN-13 목록
            title_author_list: [(title, author)] 목록
            concurrency: 동시 처리 수

        Returns:
            수집된 BookContext 목록
        """
        tasks: list[tuple[str | None, str | None, str | None]] = []

        if isbn_list:
            tasks.extend([(isbn, None, None) for isbn in isbn_list])
        if title_author_list:
            tasks.extend([(None, t, a) for t, a in title_author_list])

        semaphore = asyncio.Semaphore(concurrency)
        results: list[BookContext] = []

        async def _add_with_sem(isbn: str | None, title: str | None, author: str | None) -> BookContext | None:
            async with semaphore:
                try:
                    return await self.add_book(
                        isbn=isbn, title=title, author=author, _persist_db=False
                    )
                except Exception as e:
                    print(f"[WARN] 책 등록 실패 ({isbn or title}): {e}")
                    return None

        ctxs = await asyncio.gather(*[_add_with_sem(i, t, a) for i, t, a in tasks])
        results = [ctx for ctx in ctxs if ctx is not None]

        if self.persist_kg and self.supabase_client and results:
            await asyncio.to_thread(
                save_kg_to_supabase, self.supabase_client, self.kg
            )
        if self.persist_embeddings and self.supabase_client and results:
            await asyncio.to_thread(
                upsert_all_book_vectors, self.supabase_client, self.vector_store
            )

        print(f"\n[OK] {len(results)}/{len(tasks)}권 등록 완료")
        print(f"     KG: {self.kg.summary()}")
        print(f"     VectorStore: {len(self.vector_store)}권")
        return results

    def _update_ripplenet_scorer(self) -> None:
        """벡터 저장소의 현재 상태로 RippleNetScorer 를 갱신한다."""
        import numpy as np
        entity_vectors: dict[str, np.ndarray] = {}
        for bv in self.vector_store._books:
            book_id = f"book:{bv.isbn13}"
            entity_vectors[book_id] = bv.vector
            entity_vectors[bv.isbn13] = bv.vector

        self.ripplenet_scorer = RippleNetScorer(
            kg_store=self.kg,
            entity_vectors=entity_vectors,
            n_hops=2,
            hop_decay=0.7,
        )

        self.scorer = HybridScorer(
            kg_store=self.kg,
            vector_store=self.vector_store,
            ripplenet_scorer=self.ripplenet_scorer,
        )

        # Explainer KG 업데이트
        self.explainer.kg = self.kg
        self.explainer.path_extractor.kg = self.kg

    # ── Phase 3+4: 추천 ──────────────────────────────────────────────────────

    async def recommend(
        self,
        user_profile: UserProfile | None = None,
        top_k: int = 10,
        reference_time: datetime | None = None,
        with_explanation: bool = True,
        verbose: bool = False,
    ) -> list[ExplainedRecommendation]:
        """4단계 파이프라인을 실행해 추천 결과를 반환한다.

        Args:
            user_profile: 사용자 프로파일 (None 이면 self.user_profile 사용)
            top_k: 최종 추천 수
            reference_time: 기준 시각 (시간 감쇠 계산용)
            with_explanation: LLM 설명 생성 여부 (False 면 빠르게 동작)
            verbose: True면 Phase 3 후보 수집·상위 점수 진단 출력

        Returns:
            ExplainedRecommendation 목록
        """
        profile = user_profile or self.user_profile
        ref = reference_time or datetime.now(timezone.utc)

        if self.scorer is None:
            self._update_ripplenet_scorer()

        # Phase 3: 하이브리드 스코어링
        print("[Phase 3] 하이브리드 스코어링 중...")
        alpha = self.scorer.compute_alpha(profile)
        print(f"          동적 alpha={alpha:.3f} "
              f"(프로파일 풍부도={profile.richness:.2f})")

        scored = self.scorer.score_candidates(
            user_profile=profile,
            reference_time=ref,
            n_results=top_k * 3,
            verbose=verbose,
        )
        print(f"          스코어링 완료: 랭킹된 후보 {len(scored)}개 (top_k×3까지 탐색)")

        # Phase 4: 다양성 보정 (MMR + Epsilon-greedy)
        print("[Phase 4] 다양성 보정 (MMR + ε-greedy) 중...")
        diverse_results = self.diversity.process(scored, top_k=top_k)
        print(f"          최종 {len(diverse_results)}권 선정")

        if not with_explanation:
            return [
                ExplainedRecommendation(
                    isbn13=b.isbn13,
                    title=b.title,
                    authors=b.authors,
                    final_score=b.final_score,
                    graph_score=b.graph_score,
                    vector_score=b.vector_score,
                    alpha_used=b.alpha_used,
                    kdc_class=b.kdc_class,
                    publisher=b.publisher,
                    published_year=b.published_year,
                )
                for b in diverse_results
            ]

        # Phase 4: XAI 설명 생성
        print("[Phase 4] 추천 이유 생성 중...")
        seed_isbns = profile.get_seed_isbns(reference_time=ref)
        explained = await self.explainer.explain_batch(
            recommendations=diverse_results,
            seed_isbns=seed_isbns,
            seed_book_titles=self._book_titles,
            top_k=top_k,
        )
        print(f"[완료] {len(explained)}권 추천 생성 완료\n")
        return explained

    # ── 저장/로드 ────────────────────────────────────────────────────────────

    def save(self, save_dir: str | Path) -> None:
        """파이프라인 상태를 저장한다."""
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        self.kg.save(save_dir / "kg.pkl")
        self.vector_store.save(save_dir / "vectors.pkl")
        self.user_profile.save(save_dir / "user_profile.json")
        if self.persist_kg and self.supabase_client:
            save_kg_to_supabase(self.supabase_client, self.kg)
        if self.persist_embeddings and self.supabase_client:
            upsert_all_book_vectors(self.supabase_client, self.vector_store)
        print(f"[OK] 파이프라인 저장 완료: {save_dir}")

    def load(self, save_dir: str | Path) -> None:
        """저장된 파이프라인 상태를 로드한다."""
        save_dir = Path(save_dir)

        kg_path = save_dir / "kg.pkl"
        vec_path = save_dir / "vectors.pkl"
        profile_path = save_dir / "user_profile.json"

        if kg_path.exists():
            self.kg = NetworkXKGStore.load(kg_path)
        if vec_path.exists():
            self.vector_store = BookVectorStore.load(vec_path)
        if profile_path.exists():
            self.user_profile = UserProfile.load(profile_path)

        self._book_titles = {
            bv.isbn13: bv.title for bv in self.vector_store._books
        }
        self._update_ripplenet_scorer()
        print(f"[OK] 파이프라인 로드 완료: {save_dir}")
        print(f"     KG: {self.kg.summary()}")
        print(f"     VectorStore: {len(self.vector_store)}권")
        print(f"     User: {self.user_profile.summary()}")

    def status(self) -> dict[str, Any]:
        """현재 파이프라인 상태를 반환한다."""
        return {
            "kg_nodes": self.kg.node_count(),
            "kg_edges": self.kg.edge_count(),
            "books_registered": len(self.vector_store),
            "user_actions": self.user_profile.action_count,
            "user_unique_books": self.user_profile.unique_book_count,
            "profile_richness": round(self.user_profile.richness, 3),
            "use_supabase": self.use_supabase,
            "persist_kg": self.persist_kg,
            "persist_embeddings": self.persist_embeddings,
        }
