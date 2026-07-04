from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.repositories.supabase_repo import fetch_books_by_ids, must_supabase, ratings_map_for_books
from backend.services.books_service import now_iso

router = APIRouter(tags=["collections"])


@router.get("/api/users/{user_id}/collections")
def user_collections(user_id: str) -> dict[str, Any]:
    sb = must_supabase()
    q = (
        sb.table("collections")
        .select("collections_id, users_id, title, description, is_public, created_at")
        .eq("users_id", user_id)
        .order("created_at", desc=True)
    )
    res = q.limit(20).execute()
    collections = res.data or []
    ids = [str(c.get("collections_id") or "").strip() for c in collections if str(c.get("collections_id") or "").strip()]
    books_by_collection: dict[str, list[dict[str, Any]]] = {cid: [] for cid in ids}
    if ids:
        cb = (
            sb.table("collection_books")
            .select("books_id, collections_id, order_index")
            .in_("collections_id", ids)
            .order("order_index", desc=False)
            .execute()
        )
        rows = cb.data or []
        all_book_ids = [str(r.get("books_id") or "").strip() for r in rows if str(r.get("books_id") or "").strip()]
        books_map = fetch_books_by_ids(sb, all_book_ids)
        ratings = ratings_map_for_books(sb, list(books_map.keys()))
        for row in rows:
            cid = str(row.get("collections_id") or "").strip()
            bid = str(row.get("books_id") or "").strip()
            book = books_map.get(bid)
            if not cid or not book:
                continue
            books_by_collection.setdefault(cid, []).append({**book, "rating": ratings.get(bid, 0.0)})
    items = []
    for collection in collections:
        cid = str(collection.get("collections_id") or "").strip()
        items.append(
            {
                "id": cid,
                "userId": str(collection.get("users_id") or ""),
                "title": str(collection.get("title") or "").strip(),
                "description": str(collection.get("description") or "").strip(),
                "isPublic": bool(collection.get("is_public")),
                "createdAt": str(collection.get("created_at") or now_iso()),
                "books": books_by_collection.get(cid, []),
            }
        )
    return {"items": items}


@router.get("/api/collections/{collection_id}")
def collection_detail(collection_id: str) -> dict[str, Any]:
    sb = must_supabase()
    cres = (
        sb.table("collections")
        .select("collections_id, users_id, title, description, is_public, created_at")
        .eq("collections_id", collection_id)
        .limit(1)
        .execute()
    )
    rows = cres.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="컬렉션을 찾을 수 없습니다.")
    collection = rows[0]
    books_res = (
        sb.table("collection_books")
        .select("books_id, collections_id, order_index, added_at")
        .eq("collections_id", collection_id)
        .order("order_index", desc=False)
        .execute()
    )
    cbooks = books_res.data or []
    book_ids = [str(r.get("books_id") or "").strip() for r in cbooks if str(r.get("books_id") or "").strip()]
    books_map = fetch_books_by_ids(sb, book_ids)
    ratings = ratings_map_for_books(sb, book_ids)
    books = []
    for row in cbooks:
        bid = str(row.get("books_id") or "").strip()
        book = books_map.get(bid)
        if not book:
            continue
        books.append({**book, "rating": ratings.get(bid, 0.0)})
    return {
        "item": {
            "id": str(collection.get("collections_id") or ""),
            "userId": str(collection.get("users_id") or ""),
            "title": str(collection.get("title") or "").strip(),
            "description": str(collection.get("description") or "").strip(),
            "isPublic": bool(collection.get("is_public")),
            "createdAt": str(collection.get("created_at") or now_iso()),
            "books": books,
            "likeCount": 0,
            "comments": [],
        }
    }
