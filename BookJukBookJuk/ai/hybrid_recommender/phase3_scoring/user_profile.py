"""동적 사용자 프로파일 with 시간 감쇠 (요구사항 4)

사용자의 과거 행동 이력에 시간 감쇠 함수를 적용한다:
    Weight = exp(-λ × Δt)
    λ = 0.1 (기본값), Δt = 경과 일수

- 최근 행동: 높은 가중치
- 오래된 행동: 낮은 가중치
- 최근 30일 세션과 장기 이력을 구분하여 관리
"""
from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class ActionType(str, Enum):
    """사용자 행동 유형과 기본 가중치."""
    READ_COMPLETE = "read_complete"    # 완독: 가장 높은 신호
    READING = "reading"                # 읽는 중
    WISHLIST = "wishlist"              # 찜
    RATED_HIGH = "rated_high"          # 별점 4~5
    RATED_LOW = "rated_low"            # 별점 1~2 (부정 신호)
    SEARCHED = "searched"              # 검색
    VIEWED = "viewed"                  # 상세 조회

    @property
    def base_weight(self) -> float:
        return {
            ActionType.READ_COMPLETE: 1.0,
            ActionType.READING: 0.8,
            ActionType.RATED_HIGH: 0.9,
            ActionType.WISHLIST: 0.6,
            ActionType.SEARCHED: 0.3,
            ActionType.VIEWED: 0.2,
            ActionType.RATED_LOW: -0.5,  # 부정 신호
        }[self]


@dataclass
class UserAction:
    """단일 사용자 행동 기록."""
    isbn13: str
    action_type: ActionType
    timestamp: datetime
    rating: float | None = None       # 별점 (1~5), 선택적
    book_title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # timezone-aware 로 통일
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)


class UserProfile:
    """시간 감쇠 기반 동적 사용자 프로파일.

    Args:
        user_id: 사용자 식별자
        lambda_decay: 시간 감쇠 계수 (기본 0.1, 클수록 최근 편향)
        session_window_days: 최근 세션으로 간주하는 일수 (기본 30일)
    """

    def __init__(
        self,
        user_id: str,
        lambda_decay: float = 0.1,
        session_window_days: int = 30,
    ) -> None:
        self.user_id = user_id
        self.lambda_decay = lambda_decay
        self.session_window_days = session_window_days
        self._actions: list[UserAction] = []

    # ── 행동 추가 ────────────────────────────────────────────────────────────

    def add_action(self, action: UserAction) -> None:
        """행동을 기록한다. 동일 isbn + action_type 이면 타임스탬프를 갱신한다."""
        for i, a in enumerate(self._actions):
            if a.isbn13 == action.isbn13 and a.action_type == action.action_type:
                self._actions[i] = action
                return
        self._actions.append(action)

    def add_read(
        self,
        isbn13: str,
        book_title: str = "",
        timestamp: datetime | None = None,
        rating: float | None = None,
    ) -> None:
        """간편한 완독 기록 추가."""
        ts = timestamp or datetime.now(timezone.utc)
        action_type = ActionType.READ_COMPLETE
        if rating is not None:
            action_type = ActionType.RATED_HIGH if rating >= 3.5 else ActionType.RATED_LOW
        self.add_action(UserAction(
            isbn13=isbn13,
            action_type=action_type,
            timestamp=ts,
            rating=rating,
            book_title=book_title,
        ))

    # ── 시간 감쇠 계산 ───────────────────────────────────────────────────────

    def compute_time_weight(
        self,
        action: UserAction,
        reference_time: datetime | None = None,
    ) -> float:
        """시간 감쇠 가중치를 계산한다.

        W = base_weight × exp(-λ × Δt)
        Δt: 현재 시점 기준 경과 일수
        """
        ref = reference_time or datetime.now(timezone.utc)
        delta_days = (ref - action.timestamp).total_seconds() / 86400.0
        delta_days = max(0.0, delta_days)

        time_weight = math.exp(-self.lambda_decay * delta_days)
        base = action.action_type.base_weight

        # 별점이 있으면 base 가중치 조정
        if action.rating is not None:
            if action.rating >= 4.0:
                base = min(base * 1.2, 1.0)
            elif action.rating <= 2.0:
                base = base * 0.5

        return base * time_weight

    def get_weighted_seeds(
        self,
        reference_time: datetime | None = None,
        min_weight: float = 0.05,
    ) -> dict[str, float]:
        """각 ISBN 의 시간 감쇠 가중치를 계산한다.

        부정 신호(RATED_LOW) 를 포함해 계산하므로
        최종적으로 양수인 항목만 반환한다.

        Returns:
            {isbn13: normalized_weight} (합계 = 1.0)
        """
        isbn_weights: dict[str, float] = {}

        for action in self._actions:
            w = self.compute_time_weight(action, reference_time)
            if action.isbn13 in isbn_weights:
                isbn_weights[action.isbn13] += w
            else:
                isbn_weights[action.isbn13] = w

        # 양수 가중치만, min_weight 이상인 것만
        filtered = {
            isbn: max(0.0, w)
            for isbn, w in isbn_weights.items()
            if w >= min_weight
        }

        if not filtered:
            return {}

        total = sum(filtered.values())
        return {isbn: w / total for isbn, w in filtered.items()}

    def get_seed_isbns(
        self,
        reference_time: datetime | None = None,
        min_weight: float = 0.05,
    ) -> list[str]:
        """가중치 내림차순으로 정렬된 시드 ISBN 목록을 반환한다."""
        weighted = self.get_weighted_seeds(reference_time, min_weight)
        return sorted(weighted.keys(), key=lambda x: weighted[x], reverse=True)

    # ── 세션 분리 ────────────────────────────────────────────────────────────

    def get_recent_actions(
        self,
        reference_time: datetime | None = None,
    ) -> list[UserAction]:
        """최근 session_window_days 내의 행동 목록을 반환한다."""
        ref = reference_time or datetime.now(timezone.utc)
        cutoff = ref - timedelta(days=self.session_window_days)
        return [a for a in self._actions if a.timestamp >= cutoff]

    def get_long_term_actions(
        self,
        reference_time: datetime | None = None,
    ) -> list[UserAction]:
        """session_window_days 이전의 장기 이력을 반환한다."""
        ref = reference_time or datetime.now(timezone.utc)
        cutoff = ref - timedelta(days=self.session_window_days)
        return [a for a in self._actions if a.timestamp < cutoff]

    # ── 프로파일 풍부도 ──────────────────────────────────────────────────────

    @property
    def richness(self) -> float:
        """프로파일 풍부도 (0~1). 행동 수가 많을수록 높다.

        RippleNet 의 alpha 동적 조정에 사용된다:
        - richness 높음 → alpha 높음 (그래프 점수 신뢰)
        - richness 낮음 → alpha 낮음 (벡터 점수 의존)
        """
        n = len(self._actions)
        # sigmoid-like: 10개 행동에서 ~0.73, 30개에서 ~0.95
        return 1.0 - math.exp(-n / 10.0)

    @property
    def action_count(self) -> int:
        return len(self._actions)

    @property
    def unique_book_count(self) -> int:
        return len({a.isbn13 for a in self._actions})

    def distinct_isbn13s(self) -> list[str]:
        """이력에 등장한 ISBN 전체(중복 제거, 첫 등장 순서 유지)."""
        seen: set[str] = set()
        out: list[str] = []
        for a in self._actions:
            if a.isbn13 and a.isbn13 not in seen:
                seen.add(a.isbn13)
                out.append(a.isbn13)
        return out

    def summary(self) -> str:
        return (
            f"사용자 {self.user_id}: "
            f"행동 {self.action_count}개, "
            f"도서 {self.unique_book_count}권, "
            f"프로파일 풍부도 {self.richness:.2f}"
        )

    # ── 직렬화 ──────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "lambda_decay": self.lambda_decay,
            "session_window_days": self.session_window_days,
            "actions": [
                {
                    "isbn13": a.isbn13,
                    "action_type": a.action_type.value,
                    "timestamp": a.timestamp.isoformat(),
                    "rating": a.rating,
                    "book_title": a.book_title,
                    "metadata": a.metadata,
                }
                for a in self._actions
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        profile = cls(
            user_id=data["user_id"],
            lambda_decay=data.get("lambda_decay", 0.1),
            session_window_days=data.get("session_window_days", 30),
        )
        for ad in data.get("actions", []):
            ts = datetime.fromisoformat(ad["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            profile.add_action(UserAction(
                isbn13=ad["isbn13"],
                action_type=ActionType(ad["action_type"]),
                timestamp=ts,
                rating=ad.get("rating"),
                book_title=ad.get("book_title", ""),
                metadata=ad.get("metadata", {}),
            ))
        return profile

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> "UserProfile":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
