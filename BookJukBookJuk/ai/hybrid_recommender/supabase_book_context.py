"""Supabase `books` + `book_api_cache`에서 BookContext 조립.

`book_api_cache`는 RLS로 anon 조회가 막혀 있을 수 있어, 서비스 롤 키 사용을 권장한다.
"""
from __future__ import annotations

import json
import os
from typing import Any


def create_supabase_client_from_env() -> Any | None:
    """`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`(권장) 또는 `SUPABASE_ANON_KEY`."""
    url = os.getenv("SUPABASE_URL", "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client

        return create_client(url, key)
    except Exception as e:
        print(f"[WARN] Supabase 클라이언트 생성 실패: {e}")
        return None

from book_chat.data_collector import BookContext
from library_api import BookKeyword


def _kdc_class_from_row(kdc_no: str, kdc_nm: str) -> str:
    no = (kdc_no or "").strip()
    nm = (kdc_nm or "").strip()
    if no and nm:
        return f"{no} {nm}".strip()
    return nm or no


def _parse_keywords(raw: Any) -> list[BookKeyword]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    out: list[BookKeyword] = []
    for item in raw:
        if isinstance(item, dict):
            w = str(item.get("word") or item.get("Word") or "").strip()
            if not w:
                continue
            try:
                weight = float(item.get("weight", item.get("Weight", 1.0)))
            except (TypeError, ValueError):
                weight = 1.0
            out.append(BookKeyword(word=w, weight=weight))
        elif isinstance(item, str) and item.strip():
            out.append(BookKeyword(word=item.strip(), weight=1.0))
    return out


def _parse_str_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return [raw] if raw.strip() else []
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _parse_wiki_sections(raw: Any) -> list[dict]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for sec in raw:
        if not isinstance(sec, dict):
            continue
        title = str(sec.get("title") or "").strip()
        text = str(sec.get("text") or "").strip()
        if title or text:
            out.append({"title": title or "section", "text": text})
    return out


def _first_non_empty(*vals: str) -> str:
    for v in vals:
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _build_raw_docs(
    description: str,
    author_bio: str,
    editorial_review: str,
    wiki_book: str,
    wiki_author: str,
    wiki_sections: list[dict],
    keywords: list[BookKeyword],
) -> list[dict]:
    raw_docs: list[dict] = []
    if description:
        raw_docs.append({"text": description, "source": "books", "doc_type": "description"})
    if author_bio:
        raw_docs.append({"text": author_bio, "source": "books", "doc_type": "biography"})
    if editorial_review:
        raw_docs.append({"text": editorial_review, "source": "books", "doc_type": "review"})
    if wiki_book:
        raw_docs.append({"text": wiki_book, "source": "위키피디아", "doc_type": "summary"})
    if wiki_author:
        raw_docs.append({"text": wiki_author, "source": "위키피디아", "doc_type": "biography"})
    for sec in wiki_sections:
        raw_docs.append({
            "text": sec.get("text", ""),
            "source": "위키피디아",
            "doc_type": "section",
            "section_title": sec.get("title", ""),
        })
    if keywords:
        kw_text = ", ".join(kw.word for kw in keywords)
        raw_docs.append({"text": f"핵심 키워드: {kw_text}", "source": "정보나루", "doc_type": "keywords"})
    return raw_docs


def load_book_context_from_supabase(supabase: Any, isbn13: str) -> BookContext | None:
    """`public.books`(id=ISBN) 행을 필수로 하고, 있으면 `book_api_cache`를 병합한다.

    Returns:
        books 행이 없으면 None.
    """
    isbn = (isbn13 or "").strip()
    if not isbn:
        return None

    book_res = supabase.table("books").select("*").eq("id", isbn).limit(1).execute()
    if not getattr(book_res, "data", None):
        return None
    b = book_res.data[0]

    cache: dict[str, Any] | None = None
    try:
        cache_res = supabase.table("book_api_cache").select("*").eq("isbn", isbn).limit(1).execute()
        if cache_res.data:
            cache = cache_res.data[0]
    except Exception:
        cache = None

    title = str(b.get("title") or "").strip()
    authors = str(b.get("authors") or "").strip()

    desc_b = str(b.get("description") or "")
    bio_b = str(b.get("author_bio") or "")
    ed_b = str(b.get("editorial_review") or "")

    desc_c = str(cache.get("description") or "") if cache else ""
    bio_c = str(cache.get("author_bio") or "") if cache else ""
    ed_c = str(cache.get("editorial_review") or "") if cache else ""

    # API_Books.md: 캐시 우선(비어 있지 않을 때)
    description = _first_non_empty(desc_c, desc_b)
    author_bio = _first_non_empty(bio_c, bio_b)
    editorial_review = _first_non_empty(ed_c, ed_b)

    keywords = _parse_keywords(cache.get("keywords") if cache else None)
    subject_names = _parse_str_list(cache.get("subject_names") if cache else None)

    wiki_book = str(cache.get("wiki_book_summary") or "") if cache else ""
    wiki_author = str(cache.get("wiki_author_summary") or "") if cache else ""
    wiki_extra = _parse_wiki_sections(cache.get("wiki_extra_sections") if cache else None)

    kdc_class = _kdc_class_from_row(
        str(b.get("kdc_class_no") or ""),
        str(b.get("kdc_class_nm") or ""),
    )

    published_year = str(b.get("published_year") or "").strip()
    if published_year and len(published_year) > 4:
        published_year = published_year[:4]

    return BookContext(
        isbn13=isbn,
        title=title,
        authors=authors,
        publisher=str(b.get("publisher") or "").strip(),
        published_year=published_year,
        description=description,
        author_bio=author_bio,
        editorial_review=editorial_review,
        keywords=keywords,
        subject_names=subject_names,
        kdc_class=kdc_class,
        wiki_book_summary=wiki_book.strip(),
        wiki_author_summary=wiki_author.strip(),
        wiki_extra_sections=wiki_extra,
        raw_docs=_build_raw_docs(
            description,
            author_bio,
            editorial_review,
            wiki_book,
            wiki_author,
            wiki_extra,
            keywords,
        ),
    )
