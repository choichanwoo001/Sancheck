"""북적북적 하이브리드 추천 엔진

Knowledge Graph + RippleNet + Hybrid Scoring + XAI 를 결합한
4단계 추천 파이프라인.

빠른 시작 (프로그램 코드에서 카탈로그를 채우는 경우):
    from hybrid_recommender import HybridRecommenderPipeline, UserProfile

    pipeline = HybridRecommenderPipeline.from_env()
    await pipeline.add_books(isbn_list=[...])  # 메타: HYBRID_USE_SUPABASE / KG·임베딩: HYBRID_PERSIST_KG·HYBRID_PERSIST_EMBEDDINGS
    pipeline.user_profile.add_read("ISBN-13", "도서 제목")
    results = await pipeline.recommend(top_k=5)

서비스·CLI: 사용자 이력은 `load_user_profile_from_supabase(client, users.Key)` 로 DB에서만 로드하는 것을 권장합니다.
"""
from .pipeline import HybridRecommenderPipeline
from .phase3_scoring.user_profile import UserProfile, UserAction, ActionType
from .phase4_xai.explainer import ExplainedRecommendation
from .supabase_user_profile import load_user_profile_from_supabase

__all__ = [
    "HybridRecommenderPipeline",
    "UserProfile",
    "UserAction",
    "ActionType",
    "ExplainedRecommendation",
    "load_user_profile_from_supabase",
]
