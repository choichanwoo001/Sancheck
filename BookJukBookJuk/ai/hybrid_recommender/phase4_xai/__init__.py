"""Phase 4: 다양성 보정 및 XAI (설명 가능한 AI)

- diversity: MMR 재순위화 + Epsilon-greedy 탐색 (요구사항 5)
- explainer: KG 경로 추출 + LLM 자연어 설명 생성 (요구사항 6)
"""
from .diversity import DiversityPostProcessor, MMRReranker, EpsilonGreedyExplorer
from .explainer import RecommendationExplainer, ExplainedRecommendation

__all__ = [
    "DiversityPostProcessor",
    "MMRReranker",
    "EpsilonGreedyExplorer",
    "RecommendationExplainer",
    "ExplainedRecommendation",
]
