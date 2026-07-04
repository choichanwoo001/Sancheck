"""Supabase `ratings` / `shelves`+`shelf_books` / `book_user_states` → `UserProfile`.

레거시: `users."Key"`, `ratings."Key"`, `shelves.user_id`, `book_user_states."Key2"`.
재구성 스키마: `users_id` / `books_id` / `shelves_id` 등 — 동일 사용자 식별 문자열을 쓴다고 가정한다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .phase3_scoring.user_profile import ActionType, UserAction, UserProfile


def _parse_ts(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    return datetime.now(timezone.utc)


def _float_score(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _rating_action_type(score: float) -> ActionType:
    if score >= 4.0:
        return ActionType.RATED_HIGH
    if score <= 2.0:
        return ActionType.RATED_LOW
    return ActionType.READ_COMPLETE


def _shelf_type_to_action(shelf_type: str) -> ActionType | None:
    return {
        "쇼핑리스트": ActionType.WISHLIST,
        "읽은": ActionType.READ_COMPLETE,
        "읽는중": ActionType.READING,
        "평가한": ActionType.RATED_HIGH,
    }.get(shelf_type)


def _first_eq_query(supabase: Any, table: str, uid: str, user_columns: tuple[str, ...]) -> Any | None:
    """PostgREST 컬럼명(따옴표 포함)·스키마 차이를 흡수한다."""
    last_err: Exception | None = None
    for col in user_columns:
        try:
            return supabase.table(table).select("*").eq(col, uid).execute()
        except Exception as e:
            last_err = e
    if last_err:
        print(f"[WARN] {table} 조회 실패: {last_err}")
    return None


def _book_state_to_action(state: str) -> ActionType | None:
    return {
        "LIST": ActionType.WISHLIST,
        "READING": ActionType.READING,
        "RATED_ONLY": ActionType.RATED_HIGH,
        "REVIEW_POSTED": ActionType.READ_COMPLETE,
    }.get(state)


def _fetch_book_titles(supabase: Any, isbns: list[str]) -> dict[str, str]:
    isbns = [x for x in isbns if x and str(x).strip()]
    if not isbns:
        return {}
    out: dict[str, str] = {}
    chunk_size = 200
    for i in range(0, len(isbns), chunk_size):
        chunk = isbns[i : i + chunk_size]
        try:
            res = (
                supabase.table("books")
                .select("id, title")
                .in_("id", chunk)
                .execute()
            )
        except Exception as e:
            print(f"[WARN] books 제목 조회 실패: {e}")
            continue
        for row in res.data or []:
            bid = str(row.get("id") or "").strip()
            title = str(row.get("title") or "").strip()
            if bid:
                out[bid] = title or bid
    return out


def load_user_profile_from_supabase(supabase: Any, user_id: str) -> UserProfile:
    """DB 행을 `UserProfile` 로 옮긴다 (동일 ISBN·행동 타입은 나중 항목이 이전 타임스탬프를 덮어쓴다)."""
    if not supabase or not (user_id or "").strip():
        return UserProfile(user_id=user_id or "anonymous")

    uid = user_id.strip()
    profile = UserProfile(user_id=uid)
    events: list[tuple[datetime, UserAction]] = []

    # --- ratings ---
    rres = _first_eq_query(
        supabase,
        "ratings",
        uid,
        ("users_id", '"Key"'),
    )

    rating_rows = (rres.data if rres else None) or []
    for row in rating_rows:
        isbn = str(row.get("books_id") or row.get("Key2") or row.get("key2") or "").strip()
        if not isbn:
            continue
        score = _float_score(row.get("score"))
        ts = _parse_ts(row.get("registered_at"))
        at = _rating_action_type(score)
        events.append(
            (
                ts,
                UserAction(
                    isbn13=isbn,
                    action_type=at,
                    timestamp=ts,
                    rating=score,
                    book_title="",
                    metadata={"source": "ratings"},
                ),
            )
        )

    # --- shelves + shelf_books ---
    sres = _first_eq_query(
        supabase,
        "shelves",
        uid,
        ("users_id", "user_id"),
    )

    shelf_meta: dict[str, str] = {}
    for row in (sres.data if sres else None) or []:
        sk = str(row.get("shelves_id") or row.get("Key") or row.get("key") or "").strip()
        st = str(row.get("shelf_type") or "").strip()
        if sk:
            shelf_meta[sk] = st

    if shelf_meta:
        shelf_keys = list(shelf_meta.keys())
        sb_rows: list[dict[str, Any]] = []
        chunk_size = 100
        for i in range(0, len(shelf_keys), chunk_size):
            chunk = shelf_keys[i : i + chunk_size]
            last_sb: Exception | None = None
            for shelf_col in ("shelves_id", '"Key2"'):
                try:
                    sbres = (
                        supabase.table("shelf_books")
                        .select("*")
                        .in_(shelf_col, chunk)
                        .execute()
                    )
                    sb_rows.extend((sbres.data if sbres else None) or [])
                    last_sb = None
                    break
                except Exception as e:
                    last_sb = e
            if last_sb:
                print(f"[WARN] shelf_books 조회 실패: {last_sb}")

        for row in sb_rows:
            isbn = str(row.get("books_id") or row.get("Key") or row.get("key") or "").strip()
            sk2 = str(row.get("shelves_id") or row.get("Key2") or row.get("key2") or "").strip()
            st = shelf_meta.get(sk2, "")
            at = _shelf_type_to_action(st)
            if not isbn or at is None:
                continue
            ts = _parse_ts(row.get("added_at"))
            meta: dict[str, Any] = {"source": "shelf_books", "shelf_type": st}
            events.append(
                (
                    ts,
                    UserAction(
                        isbn13=isbn,
                        action_type=at,
                        timestamp=ts,
                        rating=None,
                        book_title="",
                        metadata=meta,
                    ),
                )
            )

    # --- book_user_states ---
    busres = _first_eq_query(
        supabase,
        "book_user_states",
        uid,
        ("users_id", '"Key2"'),
    )

    for row in (busres.data if busres else None) or []:
        isbn = str(row.get("books_id") or row.get("Key") or row.get("key") or "").strip()
        state = str(row.get("shelf_state") or "").strip()
        at = _book_state_to_action(state)
        if not isbn or at is None:
            continue
        ts = _parse_ts(row.get("updated_at"))
        events.append(
            (
                ts,
                UserAction(
                    isbn13=isbn,
                    action_type=at,
                    timestamp=ts,
                    rating=None,
                    book_title="",
                    metadata={"source": "book_user_states", "shelf_state": state},
                ),
            )
        )

    # 제목 보강
    isbns = list({e[1].isbn13 for e in events})
    titles = _fetch_book_titles(supabase, isbns)
    fixed: list[tuple[datetime, UserAction]] = []
    for ts, ua in events:
        t = titles.get(ua.isbn13, "")
        fixed.append(
            (
                ts,
                UserAction(
                    isbn13=ua.isbn13,
                    action_type=ua.action_type,
                    timestamp=ua.timestamp,
                    rating=ua.rating,
                    book_title=t or ua.book_title,
                    metadata=ua.metadata,
                ),
            )
        )
    events = fixed

    events.sort(key=lambda x: x[0])
    for _, ua in events:
        profile.add_action(ua)

    return profile
