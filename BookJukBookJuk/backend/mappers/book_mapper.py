from __future__ import annotations

import re
from typing import Any


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def default_book_image(book_id: str, cover_image_url: str | None = None) -> str:
    cover = (cover_image_url or "").strip()
    if cover:
        return cover
    return f"/api/book-cover?isbn13={book_id}"


def map_book_row(row: dict[str, Any]) -> dict[str, Any]:
    book_id = str(row.get("id") or "").strip()
    published_year = str(row.get("published_year") or "").strip()
    return {
        "id": book_id,
        "title": str(row.get("title") or "").strip(),
        "authors": str(row.get("authors") or "").strip(),
        "description": str(row.get("description") or "").strip(),
        "authorBio": str(row.get("author_bio") or "").strip(),
        "publisher": str(row.get("publisher") or "").strip(),
        "publishedYear": published_year,
        "productionYear": safe_int(re.search(r"\d{4}", published_year).group(0), 0)
        if re.search(r"\d{4}", published_year)
        else 0,
        "kdcClassNo": str(row.get("kdc_class_no") or "").strip(),
        "kdcClassNm": str(row.get("kdc_class_nm") or "").strip(),
        "category": str(row.get("kdc_class_nm") or "").split(">")[-1].strip()
        if str(row.get("kdc_class_nm") or "").strip()
        else "",
        "coverImageUrl": str(row.get("cover_image_url") or "").strip(),
        "image": default_book_image(book_id, row.get("cover_image_url")),
    }
