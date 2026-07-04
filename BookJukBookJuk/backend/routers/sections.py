from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from backend.repositories.supabase_repo import decorate_books_with_rating, fetch_books_by_ids, must_supabase, safe_float
from backend.services.books_service import recommendations, recommendations_to_books

router = APIRouter(tags=["sections"])


@router.get("/api/sections/{section_id}/books")
async def get_section_books(
    section_id: str,
    user_id: str = Query("dev_user_1", description="사용자 ID"),
    limit: int = Query(20, ge=1, le=100, description="최대 권수"),
) -> dict[str, Any]:
    sb = must_supabase()
    sid = section_id.strip()
    if sid == "recommend":
        data = await recommendations(limit=limit, user_id=user_id, with_explanation=False)
        return {"id": sid, "title": "영진님의 취향 저격", "books": recommendations_to_books(data.get("items", []))}
    if sid == "rating":
        rres = (
            sb.table("ratings")
            .select("books_id, score")
            .order("score", desc=True)
            .limit(max(limit * 3, 20))
            .execute()
        )
        rows = rres.data or []
        score_bucket: dict[str, list[float]] = {}
        for row in rows:
            bid = str(row.get("books_id") or "").strip()
            if not bid:
                continue
            score_bucket.setdefault(bid, []).append(safe_float(row.get("score"), 0.0))
        avg_rows = sorted(
            [{"id": bid, "avg": (sum(vals) / len(vals))} for bid, vals in score_bucket.items() if vals],
            key=lambda x: x["avg"],
            reverse=True,
        )[:limit]
        books_map = fetch_books_by_ids(sb, [x["id"] for x in avg_rows])
        books = []
        for row in avg_rows:
            book = books_map.get(row["id"])
            if not book:
                continue
            books.append({**book, "rating": round(float(row["avg"]), 1)})
        return {"id": sid, "title": "평균 별점이 높은 작품", "books": books}
    if sid == "wishlist":
        states_res = (
            sb.table("book_user_states")
            .select("books_id, shelf_state")
            .eq("users_id", user_id)
            .in_("shelf_state", ["LIST", "READING"])
            .limit(limit)
            .execute()
        )
        ids = [str(r.get("books_id") or "").strip() for r in (states_res.data or []) if str(r.get("books_id") or "").strip()]
        books = decorate_books_with_rating(sb, list(fetch_books_by_ids(sb, ids).values()))
        return {"id": sid, "title": "찜한 목록/이어읽기", "books": books[:limit]}
    hot_res = (
        sb.table("ratings")
        .select("books_id, score")
        .order("registered_at", desc=True)
        .limit(max(limit * 3, 20))
        .execute()
    )
    hot_ids: list[str] = []
    for row in hot_res.data or []:
        bid = str(row.get("books_id") or "").strip()
        if bid and bid not in hot_ids:
            hot_ids.append(bid)
        if len(hot_ids) >= limit:
            break
    books = decorate_books_with_rating(sb, list(fetch_books_by_ids(sb, hot_ids).values()))
    return {"id": sid or "hot", "title": "HOT 랭킹", "books": books[:limit]}


@router.get("/api/home-sections")
async def home_sections(
    user_id: str = Query("dev_user_1", description="사용자 ID"),
    limit: int = Query(4, ge=1, le=30, description="섹션별 권수"),
) -> dict[str, Any]:
    section_order = ["wishlist", "hot", "rating", "recommend"]
    sections = []
    for sid in section_order:
        sections.append(await get_section_books(section_id=sid, user_id=user_id, limit=limit))
    return {"items": sections}
