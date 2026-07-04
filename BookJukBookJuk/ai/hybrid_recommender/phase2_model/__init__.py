"""Phase 2: 임베딩 및 모델 학습

- cold_start: LLM Zero-shot 임베딩으로 콜드스타트 해결 (요구사항 3)
- ripplenet: PyTorch 기반 RippleNet 모델 구현
- vector_store: 책 단위 벡터 DB (Pinecone/numpy)
"""
from .cold_start import ColdStartEmbedder, BookTags
from .ripplenet import RippleNet, RippleNetConfig, RippleNetScorer
from .vector_store import BookVectorStore, BookVector

__all__ = [
    "ColdStartEmbedder",
    "BookTags",
    "RippleNet",
    "RippleNetConfig",
    "RippleNetScorer",
    "BookVectorStore",
    "BookVector",
]
