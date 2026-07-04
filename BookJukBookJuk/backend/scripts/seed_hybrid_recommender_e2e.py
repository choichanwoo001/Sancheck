"""하이브리드 추천 E2E용 Supabase 시드: `books` + `book_api_cache` (알라딘·정보나루·위키).

`book_chat.data_collector.collect_book_context` 로 세 소스를 한 번에 모으고,
기본 모드에서는 정보나루 KDC 번호/이름을 `fetch_book_detail`로 보강해 `books`에도 넣습니다.

`--cache-only`: `public.books`는 건드리지 않고 `book_api_cache`만 upsert (이미 카탈로그가 채워진 경우 권장).

선행 마이그레이션(저장소에 포함됨, Supabase 프로젝트에 적용 필요):
  - `backend/supabase/migrations/20260425120000_bookjuk_full_schema.sql` (books·앱·KG·book_vectors 일괄)

필요 환경 변수:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (쓰기·RLS 우회 권장)
  LIBRARY_API_KEY, ALADIN_API_KEY
  WIKI_USER_AGENT — 위키 403 시 `앱명/버전 (mailto:이메일)` 형식 권장

실행 (저장소 루트):
  python backend/scripts/seed_hybrid_recommender_e2e.py --isbn 9788937460470
  python backend/scripts/seed_hybrid_recommender_e2e.py --isbn 9788937460470 --cache-only
  python backend/scripts/seed_hybrid_recommender_e2e.py --isbn 9788937460470 9788936434120 --dry-run

KG·book_vectors 구축은 별도: `cd ai && python build_hybrid_catalog.py` (사용자 이력 ISBN, HYBRID_PERSIST_KG=1)
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

_SCRIPTS = Path(__file__).resolve().parent
REPO = _SCRIPTS.parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(REPO / "ai") not in sys.path:
    sys.path.insert(0, str(REPO / "ai"))


def _load_data_collector():
    """`book_chat` 패키지 `__init__` (openai 등) 로드 없이 `data_collector`만 로드."""
    path = REPO / "ai" / "book_chat" / "data_collector.py"
    spec = importlib.util.spec_from_file_location("_bjbk_data_collector", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_dc = _load_data_collector()
collect_book_context = _dc.collect_book_context
BookContext = _dc.BookContext

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from book_catalog_db_limits import (  # noqa: E402
    MAX_CHARS_ALADIN_COVER_URL,
    MAX_CHARS_ALADIN_LONG_TEXT,
    MAX_CHARS_ALADIN_MEDIUM_TEXT,
    MAX_CHARS_KDC_CLASS_NM,
    MAX_CHARS_KDC_CLASS_NO,
    MAX_CHARS_PUBLISHED_YEAR,
    MAX_CHARS_PUBLISHER,
    clip,
)
from library_api import fetch_book_detail  # noqa: E402


def _load_env() -> None:
    if not load_dotenv:
        return
    p = REPO / ".env"
    if p.is_file():
        load_dotenv(p)


def _keywords_json(ctx: BookContext) -> list[dict]:
    return [{"word": k.word, "weight": k.weight} for k in ctx.keywords]


def _book_row(ctx: BookContext, class_no: str, class_nm: str) -> dict:
    pub = (ctx.published_year or "")[:4] if ctx.published_year else ""
    return {
        "id": (ctx.isbn13 or "").strip(),
        "title": clip(ctx.title, MAX_CHARS_ALADIN_MEDIUM_TEXT),
        "authors": clip(ctx.authors, MAX_CHARS_ALADIN_MEDIUM_TEXT),
        "description": clip(ctx.description, MAX_CHARS_ALADIN_LONG_TEXT),
        "author_bio": clip(ctx.author_bio, MAX_CHARS_ALADIN_MEDIUM_TEXT),
        "editorial_review": clip(ctx.editorial_review, MAX_CHARS_ALADIN_LONG_TEXT),
        "publisher": clip(ctx.publisher, MAX_CHARS_PUBLISHER),
        "published_year": clip(pub, MAX_CHARS_PUBLISHED_YEAR),
        "kdc_class_no": clip(class_no, MAX_CHARS_KDC_CLASS_NO),
        "kdc_class_nm": clip(class_nm, MAX_CHARS_KDC_CLASS_NM),
        "sector": 0,
        "cover_image_url": clip("", MAX_CHARS_ALADIN_COVER_URL),
    }


def _cache_row(ctx: BookContext, ttl_days: int) -> dict:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=ttl_days)
    extra = ctx.wiki_extra_sections or []
    return {
        "isbn": (ctx.isbn13 or "").strip(),
        "description": clip(ctx.description, MAX_CHARS_ALADIN_LONG_TEXT) or None,
        "author_bio": clip(ctx.author_bio, MAX_CHARS_ALADIN_MEDIUM_TEXT) or None,
        "editorial_review": clip(ctx.editorial_review, MAX_CHARS_ALADIN_LONG_TEXT) or None,
        "keywords": _keywords_json(ctx) if ctx.keywords else None,
        "subject_names": None,
        "wiki_book_summary": (ctx.wiki_book_summary or "").strip() or None,
        "wiki_author_summary": (ctx.wiki_author_summary or "").strip() or None,
        "wiki_extra_sections": extra if extra else None,
        "cached_at": now.isoformat(),
        "expires_at": exp.isoformat(),
    }


async def _fetch_kdc(client: httpx.AsyncClient, auth_key: str, isbn: str) -> tuple[str, str]:
    if not auth_key or not isbn:
        return "", ""
    d = await fetch_book_detail(client, auth_key, isbn)
    return str(d.get("class_no") or "").strip(), str(d.get("class_nm") or "").strip()


async def seed_one(
    isbn: str,
    *,
    library_key: str,
    aladin_key: str,
    supabase: object,
    dry_run: bool,
    cache_ttl_days: int,
    cache_only: bool,
) -> None:
    isbn = isbn.strip()
    if not isbn:
        print("[skip] 빈 ISBN", file=sys.stderr)
        return

    ctx = await collect_book_context(
        isbn13=isbn,
        library_api_key=library_key,
        aladin_api_key=aladin_key,
    )

    book = None
    if not cache_only:
        async with httpx.AsyncClient(timeout=20.0) as client:
            class_no, class_nm = await _fetch_kdc(client, library_key, isbn)
        book = _book_row(ctx, class_no, class_nm)

    cache = _cache_row(ctx, cache_ttl_days)

    if dry_run:
        if cache_only:
            print(f"[dry-run] {isbn} - book_api_cache only:\n{json.dumps(cache, ensure_ascii=False, default=str, indent=2)}")
        else:
            assert book is not None
            print(f"[dry-run] {isbn} - books:\n{json.dumps(book, ensure_ascii=False, indent=2)}")
            print(f"[dry-run] {isbn} - book_api_cache:\n{json.dumps(cache, ensure_ascii=False, default=str, indent=2)}")
        return

    if not cache_only:
        assert book is not None
        supabase.table("books").upsert(book, on_conflict="id").execute()
    supabase.table("book_api_cache").upsert(cache, on_conflict="isbn").execute()
    if cache_only:
        print(f"[OK] upsert book_api_cache only: {isbn} ({ctx.title})")
    else:
        print(f"[OK] upsert books + book_api_cache: {isbn} ({ctx.title})")


async def main_async() -> None:
    _load_env()
    parser = argparse.ArgumentParser(description="하이브리드 추천용 books + book_api_cache 시드")
    parser.add_argument(
        "--isbn",
        nargs="+",
        required=True,
        help="ISBN-13 (여러 개 가능)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Supabase 쓰기 없이 수집 결과만 출력")
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="public.books 는 수정하지 않고 book_api_cache 만 upsert",
    )
    parser.add_argument(
        "--cache-ttl-days",
        type=int,
        default=365,
        help="book_api_cache.expires_at = now + 일수 (기본 365)",
    )
    args = parser.parse_args()

    library_key = os.getenv("LIBRARY_API_KEY", "").strip()
    aladin_key = os.getenv("ALADIN_API_KEY", "").strip()
    if not library_key or not aladin_key:
        print("[오류] LIBRARY_API_KEY 및 ALADIN_API_KEY 가 필요합니다.", file=sys.stderr)
        raise SystemExit(1)

    supabase = None
    if not args.dry_run:
        url = os.getenv("SUPABASE_URL", "").strip()
        key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
        if not url or not key:
            print("[오류] SUPABASE_URL 및 SUPABASE_SERVICE_ROLE_KEY(또는 ANON) 가 필요합니다.", file=sys.stderr)
            raise SystemExit(1)
        try:
            from supabase import create_client

            supabase = create_client(url, key)
        except Exception as e:
            print(f"[오류] Supabase 클라이언트 생성 실패: {e}", file=sys.stderr)
            raise SystemExit(1)

    for isbn in args.isbn:
        await seed_one(
            isbn,
            library_key=library_key,
            aladin_key=aladin_key,
            supabase=supabase,
            dry_run=args.dry_run,
            cache_ttl_days=args.cache_ttl_days,
            cache_only=args.cache_only,
        )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
