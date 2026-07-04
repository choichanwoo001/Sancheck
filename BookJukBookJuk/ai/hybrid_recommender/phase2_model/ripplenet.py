"""RippleNet: KG 기반 사용자 선호도 전파 모델 (PyTorch 구현)

논문: "RippleNet: Propagating User Preferences on the Knowledge Graph
       for Recommender Systems" (Wang et al., KDD 2018)

핵심 아이디어:
- 사용자가 읽은 책(Seed)을 시작점으로 KG 상에서 물결처럼 퍼져나가며 선호도 전파
- 각 hop 에서 candidate 와 KG 트리플 간 어텐션으로 관련성 계산
- KG 엣지 confidence 를 어텐션 가중치에 반영

RippleNetScorer (추론 전용):
- 학습된 모델 없이도 KG 구조와 OpenAI 임베딩으로 즉시 점수 계산
- 훈련 데이터 없는 초기 상황에 적합한 semantic ripple 방식
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("[WARN] PyTorch 미설치. RippleNet 학습 기능 비활성화. pip install torch")

if TYPE_CHECKING:
    from ..phase1_kg.kg_store import NetworkXKGStore

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ── 설정 데이터클래스 ─────────────────────────────────────────────────────────


@dataclass
class RippleNetConfig:
    """RippleNet 하이퍼파라미터."""
    embedding_dim: int = 64
    n_hops: int = 2
    n_memory: int = 32          # hop 당 최대 트리플 수
    kge_weight: float = 0.01    # KG 임베딩 정규화 가중치
    l2_weight: float = 1e-7     # L2 정규화 가중치
    lr: float = 0.02
    n_epochs: int = 10
    batch_size: int = 1024
    device: str = "cpu"


# ── PyTorch RippleNet 모델 ────────────────────────────────────────────────────


if TORCH_AVAILABLE:
    class RippleNet(nn.Module):
        """KG 기반 사용자 선호도 전파 추천 모델.

        Args:
            n_entities: KG 엔티티 총 개수
            n_relations: KG 관계 유형 총 개수
            config: RippleNetConfig 하이퍼파라미터
        """

        def __init__(
            self,
            n_entities: int,
            n_relations: int,
            config: RippleNetConfig | None = None,
        ) -> None:
            super().__init__()
            self.config = config or RippleNetConfig()
            dim = self.config.embedding_dim
            n_hops = self.config.n_hops

            # 엔티티 임베딩 행렬 E ∈ R^{|E| × d}
            self.entity_emb = nn.Embedding(n_entities, dim)
            # 관계 임베딩 행렬 R ∈ R^{|R| × d × d} (bilinear 변환용)
            self.relation_emb = nn.Embedding(n_relations, dim * dim)

            # 출력 레이어 (hop 별 메모리 → 최종 user representation)
            self.transform_weights = nn.ParameterList([
                nn.Parameter(torch.ones(1)) for _ in range(n_hops)
            ])

            nn.init.xavier_uniform_(self.entity_emb.weight)
            nn.init.xavier_uniform_(self.relation_emb.weight.view(n_relations, dim, dim))

        def forward(
            self,
            item_indices: "torch.Tensor",
            ripple_sets: list[list["torch.Tensor"]],
        ) -> "torch.Tensor":
            """
            Args:
                item_indices: [batch_size] — 추천 후보 아이템 인덱스
                ripple_sets: n_hops × [heads, relations, tails]
                    각 hop 별 (head_idx [b×m], relation_idx [b×m], tail_idx [b×m])

            Returns:
                scores: [batch_size] sigmoid 확률
            """
            # 아이템 임베딩 v ∈ R^{batch × d}
            item_emb = self.entity_emb(item_indices)  # [b, d]

            # Ripple propagation
            user_memory = self._get_user_memory(item_emb, ripple_sets)

            # 최종 점수: sigmoid(v · u)
            scores = torch.sigmoid(torch.sum(item_emb * user_memory, dim=1))
            return scores

        def _get_user_memory(
            self,
            item_emb: "torch.Tensor",
            ripple_sets: list[list["torch.Tensor"]],
        ) -> "torch.Tensor":
            """사용자 메모리를 hop 별로 계산한다.

            o_h = Σ p_i × e_{t_i}
            p_i = softmax(v^T R_r e_h)
            """
            dim = self.config.embedding_dim
            batch_size = item_emb.shape[0]

            user_memories: list["torch.Tensor"] = []

            for hop, (head_idx, rel_idx, tail_idx) in enumerate(ripple_sets):
                # head_idx, rel_idx, tail_idx: [batch, n_memory]
                head_emb = self.entity_emb(head_idx)    # [b, m, d]
                tail_emb = self.entity_emb(tail_idx)    # [b, m, d]
                rel_matrix = self.relation_emb(rel_idx)  # [b, m, d*d]
                rel_matrix = rel_matrix.view(-1, self.config.n_memory, dim, dim)

                # v^T R_r e_h: [b, m]
                # item_emb: [b, d] → [b, 1, 1, d]
                v = item_emb.unsqueeze(1).unsqueeze(1)  # [b, 1, 1, d]
                # R_r e_h: [b, m, d]
                Rh = torch.matmul(rel_matrix, head_emb.unsqueeze(-1)).squeeze(-1)
                # v^T (R_r e_h): [b, m]
                attn_scores = torch.sum(v.squeeze(1) * Rh, dim=-1)  # [b, m]
                attn_weights = F.softmax(attn_scores, dim=-1)       # [b, m]

                # 메모리 o_h = Σ p_i × e_{t_i}: [b, d]
                o_h = torch.bmm(attn_weights.unsqueeze(1), tail_emb).squeeze(1)
                user_memories.append(self.transform_weights[hop] * o_h)

            # 모든 hop 의 메모리 합산
            user_memory = sum(user_memories)
            return user_memory

        def kg_loss(
            self,
            head_idx: "torch.Tensor",
            rel_idx: "torch.Tensor",
            tail_idx: "torch.Tensor",
        ) -> "torch.Tensor":
            """TransE 기반 KG 임베딩 정규화 손실."""
            dim = self.config.embedding_dim
            h = self.entity_emb(head_idx)
            t = self.entity_emb(tail_idx)
            r_matrix = self.relation_emb(rel_idx).view(-1, dim, dim)
            # Rh 근사: h^T R ≈ t
            Rh = torch.bmm(r_matrix, h.unsqueeze(-1)).squeeze(-1)
            return torch.mean(torch.sum((Rh - t) ** 2, dim=-1))

    # ── 학습 유틸 ───────────────────────────────────────────────────────────

    class RippleNetTrainer:
        """RippleNet 훈련 관리자.

        사용자 피드백 데이터 (isbn13, 읽음여부) 가 쌓이면 호출한다.
        """

        def __init__(
            self,
            model: RippleNet,
            config: RippleNetConfig,
        ) -> None:
            self.model = model
            self.config = config
            self.optimizer = torch.optim.Adam(
                model.parameters(), lr=config.lr, weight_decay=config.l2_weight
            )

        def train_step(
            self,
            item_indices: "torch.Tensor",
            labels: "torch.Tensor",
            ripple_sets: list[list["torch.Tensor"]],
            kg_triples: tuple["torch.Tensor", "torch.Tensor", "torch.Tensor"] | None = None,
        ) -> float:
            self.model.train()
            self.optimizer.zero_grad()

            scores = self.model(item_indices, ripple_sets)
            rec_loss = F.binary_cross_entropy(scores, labels.float())

            total_loss = rec_loss
            if kg_triples is not None:
                h, r, t = kg_triples
                kg_l = self.model.kg_loss(h, r, t)
                total_loss = rec_loss + self.config.kge_weight * kg_l

            total_loss.backward()
            self.optimizer.step()
            return total_loss.item()

        def save(self, path: str) -> None:
            torch.save({
                "model_state": self.model.state_dict(),
                "config": self.config,
            }, path)

        @classmethod
        def load(
            cls,
            path: str,
            n_entities: int,
            n_relations: int,
        ) -> tuple["RippleNet", "RippleNetTrainer"]:
            checkpoint = torch.load(path, map_location="cpu")
            config = checkpoint["config"]
            model = RippleNet(n_entities, n_relations, config)
            model.load_state_dict(checkpoint["model_state"])
            trainer = cls(model, config)
            return model, trainer

else:
    # PyTorch 없을 때 더미 클래스
    class RippleNet:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise ImportError("RippleNet 사용을 위해 torch 를 설치하세요: pip install torch")

    class RippleNetTrainer:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise ImportError("RippleNetTrainer 사용을 위해 torch 를 설치하세요: pip install torch")


# ── RippleNetScorer (추론 전용, PyTorch 불필요) ───────────────────────────────


class RippleNetScorer:
    """PyTorch 없이도 동작하는 Semantic Ripple 추론기.

    학습된 모델이 없는 초기 상황에서 OpenAI 임베딩 + KG 구조만으로
    사용자 선호도를 전파하여 점수를 계산한다.

    알고리즘:
    1. Seed books 의 임베딩 벡터를 가중 평균 → 사용자 preference vector
    2. 각 hop 에서 KG 이웃 노드로 확산 (confidence 가중)
    3. candidate 와 최종 확산 벡터 간 코사인 유사도 → Graph Score
    """

    def __init__(
        self,
        kg_store: "NetworkXKGStore",
        entity_vectors: dict[str, np.ndarray],
        n_hops: int = 2,
        hop_decay: float = 0.7,
    ) -> None:
        """
        Args:
            kg_store: 지식 그래프 저장소
            entity_vectors: {entity_id: 임베딩 벡터} 매핑
            n_hops: ripple 전파 hop 수 (1~3)
            hop_decay: hop 이 멀어질수록 선호도 감쇠 계수 (0~1)
        """
        self.kg = kg_store
        self.entity_vectors = entity_vectors
        self.n_hops = n_hops
        self.hop_decay = hop_decay

    def _get_vec(self, entity_id: str) -> np.ndarray | None:
        vec = self.entity_vectors.get(entity_id)
        if vec is not None:
            return vec
        # label 기반 폴백 (entity_id 가 'book:...' 형태인 경우 title 매핑 시도)
        label = entity_id.split(":", 1)[-1] if ":" in entity_id else entity_id
        for eid, v in self.entity_vectors.items():
            if eid.endswith(label) or label in eid:
                return v
        return None

    def _build_user_preference(
        self,
        seed_isbns: list[str],
        seed_weights: dict[str, float],
    ) -> np.ndarray | None:
        """시드 책들의 가중 평균 선호도 벡터를 계산한다."""
        vecs: list[np.ndarray] = []
        weights: list[float] = []

        for isbn in seed_isbns:
            book_id = f"book:{isbn}"
            vec = self._get_vec(book_id)
            if vec is None:
                vec = self._get_vec(isbn)
            if vec is not None:
                vecs.append(vec)
                weights.append(seed_weights.get(isbn, 1.0))

        if not vecs:
            return None

        w = np.array(weights, dtype=np.float32)
        w /= w.sum()
        user_pref = sum(wi * vi for wi, vi in zip(w, vecs))
        norm = np.linalg.norm(user_pref)
        return user_pref / norm if norm > 0 else user_pref

    def _ripple_expand(
        self,
        seed_ids: list[str],
        hop: int,
    ) -> dict[str, float]:
        """KG 를 따라 hop 번 확산된 엔티티와 누적 가중치를 반환한다."""
        # entity_id → cumulative_weight
        current: dict[str, float] = {sid: 1.0 for sid in seed_ids}

        for h in range(hop):
            next_layer: dict[str, float] = {}
            for entity_id, w in current.items():
                neighbors = self.kg.get_neighbors(entity_id, min_confidence=0.4)
                for neighbor_id, rel, conf in neighbors:
                    hop_w = w * conf * (self.hop_decay ** (h + 1))
                    if neighbor_id in next_layer:
                        next_layer[neighbor_id] = max(next_layer[neighbor_id], hop_w)
                    else:
                        next_layer[neighbor_id] = hop_w
            current.update(next_layer)

        return current

    def score(
        self,
        seed_isbns: list[str],
        candidate_isbns: list[str],
        seed_weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """사용자 이력과 후보 책들의 KG 기반 점수를 계산한다.

        Args:
            seed_isbns: 사용자가 읽은 책 ISBN 목록
            candidate_isbns: 점수를 계산할 후보 ISBN 목록
            seed_weights: 각 시드 책의 가중치 (시간 감쇠 적용값)

        Returns:
            {isbn: score} 형태의 점수 딕셔너리 (0~1)
        """
        if not seed_isbns:
            return {isbn: 0.0 for isbn in candidate_isbns}

        w = seed_weights or {isbn: 1.0 for isbn in seed_isbns}

        # 사용자 preference 벡터 계산
        user_pref = self._build_user_preference(seed_isbns, w)

        # KG 확산: seed 로부터 n_hops 만큼 이웃 노드 집합 생성
        seed_entity_ids = [f"book:{isbn}" for isbn in seed_isbns]
        expanded = self._ripple_expand(seed_entity_ids, self.n_hops)

        scores: dict[str, float] = {}
        for isbn in candidate_isbns:
            book_id = f"book:{isbn}"
            score = 0.0

            # 방법 1: KG 확산에서 candidate 가 직접 도달되는 경우
            if book_id in expanded:
                score = max(score, expanded[book_id])

            # 방법 2: candidate 의 KG 이웃과 확산 집합의 겹침 계산
            neighbors = self.kg.get_neighbors(book_id, min_confidence=0.3)
            for neighbor_id, rel, conf in neighbors:
                if neighbor_id in expanded:
                    overlap_score = expanded[neighbor_id] * conf * 0.5
                    score = max(score, overlap_score)

            # 방법 3: 임베딩 유사도 (벡터가 있을 때)
            if user_pref is not None:
                cand_vec = self._get_vec(book_id)
                if cand_vec is None:
                    cand_vec = self._get_vec(isbn)
                if cand_vec is not None:
                    cosine = float(np.dot(user_pref, cand_vec))
                    cosine = max(0.0, cosine)
                    score = 0.6 * score + 0.4 * cosine

            scores[isbn] = min(1.0, score)

        return scores
