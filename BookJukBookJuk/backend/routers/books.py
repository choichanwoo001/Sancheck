from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from backend.services import books_service

router = APIRouter(tags=["books"])


@router.get("/api/book-cover")
def book_cover(isbn13: str = Query(..., alias="isbn13", description="ISBN-13")) -> RedirectResponse:
    return RedirectResponse(url=books_service.book_cover(isbn13), status_code=302)


@router.get("/api/recommendations")
async def recommendations(
    limit: int = Query(4, ge=1, le=30, description="추천 권수"),
    user_id: str = Query(
        "dev_user_1",
        description="Supabase users.users_id 와 동일한 사용자 식별자",
    ),
    with_explanation: bool = Query(
        False,
        description="True면 LLM 설명 생성(느림). 홈 행에는 false 권장.",
    ),
) -> dict[str, Any]:
    return await books_service.recommendations(limit=limit, user_id=user_id, with_explanation=with_explanation)


@router.get("/api/books/search")
def search_books(
    q: str = Query("", description="검색어(제목/저자)"),
    limit: int = Query(20, ge=1, le=100, description="최대 결과 수"),
) -> dict[str, Any]:
    return books_service.search_books(query=q, limit=limit)


@router.get("/api/books/{book_id}")
def get_book_detail(book_id: str) -> dict[str, Any]:
    return books_service.get_book_detail(book_id)


@router.get("/api/books/{book_id}/comments")
def get_book_comments(
    book_id: str,
    limit: int = Query(20, ge=1, le=100, description="최대 코멘트 수"),
) -> dict[str, Any]:
    return books_service.get_book_comments(book_id, limit)


@router.get("/api/books/{book_id}/comments/{comment_id}")
def get_book_comment_detail(book_id: str, comment_id: str) -> dict[str, Any]:
    return books_service.get_book_comment_detail(book_id, comment_id)
