from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException

from backend.mappers.book_mapper import map_book_row


BOOK_COLUMNS = (
    "id, title, authors, description, author_bio, publisher, "
    "published_year, kdc_class_no, kdc_class_nm, cover_image_url"
)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def supabase_client() -> Any | None:
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client

        return create_client(url, key)
    except Exception:
        return None


def must_supabase() -> Any:
    sb = supabase_client()
    if not sb:
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY(또는 ANON_KEY) 설정이 필요합니다.",
        )
    return sb


def fetch_books_by_ids(sb: Any, book_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = [str(x).strip() for x in book_ids if str(x).strip()]
    if not ids:
        return {}
    res = sb.table("books").select(BOOK_COLUMNS).in_("id", ids).execute()
    data = res.data or []
    return {str(row.get("id")): map_book_row(row) for row in data}


def ratings_map_for_books(sb: Any, book_ids: list[str]) -> dict[str, float]:
    ids = [str(x).strip() for x in book_ids if str(x).strip()]
    if not ids:
        return {}
    res = sb.table("ratings").select("books_id, score").in_("books_id", ids).execute()
    rows = res.data or []
    bucket: dict[str, list[float]] = {}
    for row in rows:
        bid = str(row.get("books_id") or "").strip()
        if not bid:
            continue
        bucket.setdefault(bid, []).append(safe_float(row.get("score"), 0.0))
    out: dict[str, float] = {}
    for bid, scores in bucket.items():
        if scores:
            out[bid] = round(sum(scores) / len(scores), 1)
    return out


def decorate_books_with_rating(sb: Any, books: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [str(b.get("id") or "") for b in books]
    ratings = ratings_map_for_books(sb, ids)
    out = []
    for book in books:
        bid = str(book.get("id") or "")
        out.append({**book, "rating": ratings.get(bid, 0.0)})
    return out
