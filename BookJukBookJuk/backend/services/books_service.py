from __future__ import annotations

from datetime import datetime, timezone
import os
import re
from typing import Any

import httpx
from fastapi import HTTPException

from backend.mappers.book_mapper import default_book_image, map_book_row
from backend.repositories.supabase_repo import (
    BOOK_COLUMNS,
    decorate_books_with_rating,
    must_supabase,
    ratings_map_for_books,
    safe_float,
)

ALADIN_LOOKUP = "https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def aladin_key() -> str:
    return (os.getenv("ALADIN_API_KEY") or os.getenv("ALADIN_TTB_KEY") or "").strip()


def normalize_isbn(isbn: str) -> str:
    return re.sub(r"[^0-9X]", "", isbn, flags=re.I)


def book_cover(isbn13: str) -> str:
    isbn = normalize_isbn(isbn13)
    open_lib = f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"
    if len(isbn) != 13:
        return "https://covers.openlibrary.org/b/isbn/9788936434120-M.jpg"

    key = aladin_key()
    if not key:
        return open_lib
    try:
        params = {
            "ttbkey": key,
            "itemIdType": "ISBN13",
            "ItemId": isbn,
            "output": "js",
            "Version": "20131101",
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.get(ALADIN_LOOKUP, params=params)
        response.raise_for_status()
        data = response.json()
        raw = data.get("item")
        items = raw if isinstance(raw, list) else ([raw] if raw else [])
        item = items[0] if items else {}
        cover = item.get("cover")
        if isinstance(cover, str) and re.match(r"^https?://", cover, re.I):
            return cover
    except Exception:
        pass
    return open_lib


async def recommendations(limit: int, user_id: str, with_explanation: bool) -> dict[str, Any]:
    try:
        from hybrid_recommender import HybridRecommenderPipeline
        from hybrid_recommender.supabase_user_profile import load_user_profile_from_supabase
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"hybrid_recommender 로드 실패: {exc}") from exc

    try:
        pipeline = HybridRecommenderPipeline.from_env(user_id=user_id.strip() or "dev_user_1")
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    sb = pipeline.supabase_client
    if sb and user_id.strip():
        pipeline.user_profile = load_user_profile_from_supabase(sb, user_id.strip())

    if pipeline.kg.node_count() == 0 and len(pipeline.vector_store) == 0:
        raise HTTPException(
            status_code=503,
            detail="추천 엔진에 로드된 KG/벡터가 없습니다. Supabase 시드 및 HYBRID_PERSIST_* 설정을 확인하세요.",
        )

    try:
        results = await pipeline.recommend(top_k=limit, with_explanation=with_explanation)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"recommend 실패: {exc!s}") from exc

    items = []
    for result in results:
        items.append(
            {
                "id": result.isbn13,
                "isbn13": result.isbn13,
                "title": result.title,
                "authors": result.authors or "",
                "final_score": result.final_score,
                "graph_score": result.graph_score,
                "vector_score": result.vector_score,
                "alpha_used": result.alpha_used,
                "kdc_class": result.kdc_class or "",
                "publisher": result.publisher or "",
                "published_year": result.published_year or "",
                "explanation": getattr(result, "explanation", None) or "",
            }
        )
    return {"items": items}


def search_books(query: str, limit: int) -> dict[str, Any]:
    sb = must_supabase()
    cleaned = query.strip()
    if not cleaned:
        return {"items": []}
    like = f"%{cleaned}%"
    res = sb.table("books").select(BOOK_COLUMNS).or_(f"title.ilike.{like},authors.ilike.{like}").limit(limit).execute()
    books = [map_book_row(row) for row in (res.data or [])]
    return {"items": decorate_books_with_rating(sb, books)}


def get_book_detail(book_id: str) -> dict[str, Any]:
    sb = must_supabase()
    res = sb.table("books").select(BOOK_COLUMNS).eq("id", book_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="책을 찾을 수 없습니다.")
    base = map_book_row(rows[0])
    rating_map = ratings_map_for_books(sb, [book_id])
    return {
        **base,
        "rating": rating_map.get(book_id, 0.0),
        "pages": 0,
        "ageRating": "",
        "storeLocation": {"lat": 37.5665, "lng": 126.978},
    }


def get_book_comments(book_id: str, limit: int) -> dict[str, Any]:
    sb = must_supabase()
    reviews_res = (
        sb.table("reviews")
        .select("reviews_id, users_id, content, created_at")
        .eq("books_id", book_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    reviews = reviews_res.data or []
    if not reviews:
        return {"items": []}

    review_ids = [str(r.get("reviews_id") or "").strip() for r in reviews if str(r.get("reviews_id") or "").strip()]
    user_ids = list({str(r.get("users_id") or "").strip() for r in reviews if str(r.get("users_id") or "").strip()})

    rating_map: dict[str, float] = {}
    if user_ids:
        rres = sb.table("ratings").select("users_id, score").eq("books_id", book_id).in_("users_id", user_ids).execute()
        for row in (rres.data or []):
            rating_map[str(row.get("users_id") or "")] = safe_float(row.get("score"), 0.0)

    user_map: dict[str, str] = {}
    if user_ids:
        ures = sb.table("users").select("users_id, nickname").in_("users_id", user_ids).execute()
        for row in (ures.data or []):
            user_map[str(row.get("users_id") or "")] = str(row.get("nickname") or "").strip()

    reply_count_map: dict[str, int] = {rid: 0 for rid in review_ids}
    like_count_map: dict[str, int] = {rid: 0 for rid in review_ids}
    if review_ids:
        comments_res = sb.table("comments").select("reviews_id").in_("reviews_id", review_ids).execute()
        for row in (comments_res.data or []):
            rid = str(row.get("reviews_id") or "").strip()
            if rid:
                reply_count_map[rid] = reply_count_map.get(rid, 0) + 1

        likes_res = sb.table("review_likes").select("reviews_id").in_("reviews_id", review_ids).execute()
        for row in (likes_res.data or []):
            rid = str(row.get("reviews_id") or "").strip()
            if rid:
                like_count_map[rid] = like_count_map.get(rid, 0) + 1

    items = []
    for review in reviews:
        rid = str(review.get("reviews_id") or "")
        uid = str(review.get("users_id") or "")
        items.append(
            {
                "id": rid,
                "reviewId": rid,
                "userId": uid,
                "userName": user_map.get(uid) or uid or "독자",
                "text": str(review.get("content") or "").strip(),
                "rating": rating_map.get(uid, 0.0),
                "likeCount": like_count_map.get(rid, 0),
                "replyCount": reply_count_map.get(rid, 0),
                "createdAt": str(review.get("created_at") or now_iso()),
            }
        )
    return {"items": items}


def get_book_comment_detail(book_id: str, comment_id: str) -> dict[str, Any]:
    sb = must_supabase()
    comment_res = (
        sb.table("reviews")
        .select("reviews_id, users_id, content, created_at")
        .eq("books_id", book_id)
        .eq("reviews_id", comment_id)
        .limit(1)
        .execute()
    )
    rows = comment_res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="코멘트를 찾을 수 없습니다.")
    review = rows[0]
    comments = get_book_comments(book_id, limit=1000).get("items", [])
    target = next((c for c in comments if c.get("id") == comment_id), None)
    if not target:
        target = {
            "id": comment_id,
            "reviewId": comment_id,
            "userId": str(review.get("users_id") or ""),
            "userName": str(review.get("users_id") or "독자"),
            "text": str(review.get("content") or "").strip(),
            "rating": 0.0,
            "likeCount": 0,
            "replyCount": 0,
            "createdAt": str(review.get("created_at") or now_iso()),
        }
    return {"item": target}


def recommendations_to_books(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "authors": str(item.get("authors") or ""),
            "image": default_book_image(str(item.get("id") or ""), ""),
            "rating": round(safe_float(item.get("final_score"), 0.0), 2),
        }
        for item in items
    ]
