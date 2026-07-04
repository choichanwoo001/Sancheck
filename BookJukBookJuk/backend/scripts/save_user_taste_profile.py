"""Supabase 사용자 취향 스냅샷 저장 스크립트.

`ratings` / `shelves`+`shelf_books` / `book_user_states`를 UserProfile로 읽고,
시간감쇠 기반 시드 가중치 등을 `public.user_taste_profiles`에 upsert 한다.

예시:
  python backend/scripts/save_user_taste_profile.py --user-id dev_test_user_1
  python backend/scripts/save_user_taste_profile.py --user-id dev_test_user_1 --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
REPO = _SCRIPTS.parent.parent
AI_DIR = REPO / "ai"

if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from hybrid_recommender.supabase_user_profile import load_user_profile_from_supabase

DEFAULT_USER_ID = "dev_test_user_1"
DEFAULT_PROFILE_VERSION = "v1"
DEFAULT_LAMBDA_DECAY = 0.1
DEFAULT_SOURCE_WINDOW_DAYS = 30


def _load_env() -> None:
    if not load_dotenv:
        return
    p = REPO / ".env"
    if p.is_file():
        load_dotenv(p)


def _create_client():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        print("[오류] SUPABASE_URL 및 SUPABASE_SERVICE_ROLE_KEY 가 필요합니다.", file=sys.stderr)
        raise SystemExit(1)
    try:
        from supabase import create_client

        return create_client(url, key)
    except Exception as e:
        print(f"[오류] Supabase 클라이언트 생성 실패: {e}", file=sys.stderr)
        raise SystemExit(1)


def _parse_top_level_genre(kdc_class_nm: str) -> str:
    raw = (kdc_class_nm or "").strip()
    if not raw:
        return "미분류"
    return raw.split(">")[0].strip() or "미분류"


def _parse_authors_field(authors: str) -> list[str]:
    raw = (authors or "").strip()
    if not raw:
        return []
    parts = re.split(r"[,，、·/|]+", raw)
    out = []
    for p in parts:
        n = re.sub(r"\s+", " ", p).strip()
        if n:
            out.append(n)
    return out


def _compute_alpha_suggested(richness: float, alpha_min: float = 0.1, alpha_max: float = 0.7) -> float:
    r = max(0.0, min(1.0, float(richness)))
    return alpha_min + (alpha_max - alpha_min) * r


def _fetch_books_meta(sb: Any, isbns: list[str]) -> dict[str, dict[str, Any]]:
    ids = [x for x in isbns if str(x).strip()]
    if not ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    chunk_size = 200
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        res = (
            sb.table("books")
            .select("id, authors, kdc_class_nm")
            .in_("id", chunk)
            .execute()
        )
        for row in res.data or []:
            bid = str(row.get("id") or "").strip()
            if bid:
                out[bid] = row
    return out


def _build_weights_by_meta(seed_weights: dict[str, float], books_meta: dict[str, dict[str, Any]]) -> tuple[dict[str, float], dict[str, float]]:
    genre_scores: dict[str, float] = defaultdict(float)
    author_scores: dict[str, float] = defaultdict(float)

    for isbn, weight in seed_weights.items():
        row = books_meta.get(isbn) or {}
        genre = _parse_top_level_genre(str(row.get("kdc_class_nm") or ""))
        genre_scores[genre] += float(weight)

        authors = _parse_authors_field(str(row.get("authors") or ""))
        if authors:
            share = float(weight) / len(authors)
            for a in authors:
                author_scores[a] += share

    def _normalize(scores: dict[str, float]) -> dict[str, float]:
        filtered = {k: v for k, v in scores.items() if v > 0}
        total = sum(filtered.values())
        if total <= 0:
            return {}
        norm = {k: round(v / total, 6) for k, v in filtered.items()}
        return dict(sorted(norm.items(), key=lambda x: x[1], reverse=True))

    return _normalize(dict(genre_scores)), _normalize(dict(author_scores))


def _build_recent_actions_summary(profile_dict: dict[str, Any], top_n: int = 20) -> list[dict[str, Any]]:
    actions = list(profile_dict.get("actions") or [])
    actions.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    out: list[dict[str, Any]] = []
    for a in actions[:top_n]:
        out.append(
            {
                "isbn13": str(a.get("isbn13") or ""),
                "action_type": str(a.get("action_type") or ""),
                "timestamp": str(a.get("timestamp") or ""),
                "rating": a.get("rating"),
                "book_title": str(a.get("book_title") or ""),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    _load_env()
    sb = _create_client()

    user_id = (args.user_id or "").strip()
    if not user_id:
        print("[오류] --user-id 가 비었습니다.", file=sys.stderr)
        raise SystemExit(1)

    profile = load_user_profile_from_supabase(sb, user_id)
    ref = datetime.now(timezone.utc)
    seed_weights = profile.get_weighted_seeds(reference_time=ref)
    seed_weights = dict(sorted(seed_weights.items(), key=lambda x: x[1], reverse=True))

    books_meta = _fetch_books_meta(sb, list(seed_weights.keys()))
    genre_weights, author_weights = _build_weights_by_meta(seed_weights, books_meta)

    profile_dict = profile.to_dict()
    richness = float(profile.richness)
    alpha_suggested = _compute_alpha_suggested(richness)

    row = {
        "users_id": user_id,
        "profile_version": args.profile_version,
        "computed_at": ref.isoformat(),
        "seed_weights": seed_weights,
        "genre_weights": genre_weights,
        "author_weights": author_weights,
        "richness": richness,
        "alpha_suggested": alpha_suggested,
        "lambda_decay": float(profile_dict.get("lambda_decay", DEFAULT_LAMBDA_DECAY)),
        "source_window_days": int(profile_dict.get("session_window_days", DEFAULT_SOURCE_WINDOW_DAYS)),
        "action_count": int(profile.action_count),
        "unique_book_count": int(profile.unique_book_count),
        "recent_actions_summary": _build_recent_actions_summary(profile_dict, top_n=args.recent_actions_limit),
        "model_meta": {
            "source": "hybrid_recommender.supabase_user_profile",
            "alpha_formula": "alpha_min + (alpha_max-alpha_min) * richness",
            "alpha_min": 0.1,
            "alpha_max": 0.7,
        },
    }

    if args.dry_run:
        print("[dry-run] user_taste_profiles 업서트 생략")
        print(f" users_id={user_id}")
        print(f" action_count={row['action_count']}, unique_book_count={row['unique_book_count']}")
        print(f" richness={row['richness']:.4f}, alpha_suggested={row['alpha_suggested']:.4f}")
        print(f" seed_weights={len(seed_weights)}개, genre_weights={len(genre_weights)}개, author_weights={len(author_weights)}개")
        return

    try:
        sb.table("user_taste_profiles").upsert(row, on_conflict="users_id").execute()
    except Exception as e:
        print(
            "[오류] user_taste_profiles 업서트 실패. "
            "테이블/권한(RLS 정책) 적용 여부를 확인하세요.",
            file=sys.stderr,
        )
        print(f"       상세: {e}", file=sys.stderr)
        raise SystemExit(1)

    print("[OK] user_taste_profiles 저장 완료")
    print(f" users_id={user_id}")
    print(f" action_count={row['action_count']}, unique_book_count={row['unique_book_count']}")
    print(f" richness={row['richness']:.4f}, alpha_suggested={row['alpha_suggested']:.4f}")
    print(f" seed_weights={len(seed_weights)}개, genre_weights={len(genre_weights)}개, author_weights={len(author_weights)}개")


def main() -> None:
    p = argparse.ArgumentParser(description="사용자 취향 스냅샷을 user_taste_profiles 에 저장")
    p.add_argument("--user-id", type=str, default=DEFAULT_USER_ID, help=f"대상 users_id (기본 {DEFAULT_USER_ID})")
    p.add_argument(
        "--profile-version",
        type=str,
        default=DEFAULT_PROFILE_VERSION,
        help=f"profile_version 값 (기본 {DEFAULT_PROFILE_VERSION})",
    )
    p.add_argument(
        "--recent-actions-limit",
        type=int,
        default=20,
        help="recent_actions_summary 에 담을 최근 행동 수 (기본 20)",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if args.recent_actions_limit < 1:
        print("[오류] --recent-actions-limit 은 1 이상이어야 합니다.", file=sys.stderr)
        raise SystemExit(1)
    run(args)


if __name__ == "__main__":
    main()
