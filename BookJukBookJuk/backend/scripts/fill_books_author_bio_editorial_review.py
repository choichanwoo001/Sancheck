"""Supabase books의 author_bio / editorial_review 컬럼만 보강 업데이트.

기존 책 메타(title, authors, description 등)는 건드리지 않고,
책 id(ISBN13)를 기준으로 알라딘 ItemLookUp에서 두 컬럼만 채운다.

실행 (저장소 루트):
  python backend/scripts/fill_books_author_bio_editorial_review.py
  python backend/scripts/fill_books_author_bio_editorial_review.py --all
  python backend/scripts/fill_books_author_bio_editorial_review.py --limit 200 --dry-run
  python backend/scripts/fill_books_author_bio_editorial_review.py --wiki-only --wikipedia-author-bio --wiki-user-agent "BookJukBookJukBot/1.0 (https://example.com; you@example.com)"
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from book_catalog_db_limits import MAX_CHARS_ALADIN_LONG_TEXT, MAX_CHARS_ALADIN_MEDIUM_TEXT, clip

ALADIN_BASE = "https://www.aladin.co.kr/ttb/api"
WIKI_API_BASE = "https://{lang}.wikipedia.org/w/api.php"
WIKI_SUMMARY_BASE = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
REPO = Path(__file__).resolve().parent.parent.parent
BATCH = 200


def _load_env() -> None:
    if not load_dotenv:
        return
    p = REPO / ".env"
    if p.is_file():
        load_dotenv(p)


def _extract_author_bio_and_editorial_review(aladin: dict) -> tuple[str, str]:
    sub_info = aladin.get("subInfo") if isinstance(aladin.get("subInfo"), dict) else {}

    author_bio_parts: list[str] = []
    author_candidates = [
        aladin.get("authorInfo"),
        sub_info.get("authorInfo"),
        aladin.get("authorInfoAdd"),
        sub_info.get("authorInfoAdd"),
    ]
    for candidate in author_candidates:
        if isinstance(candidate, str):
            txt = candidate.strip()
            if txt:
                author_bio_parts.append(txt)
        elif isinstance(candidate, dict):
            txt = str(candidate.get("authorInfo") or candidate.get("info") or "").strip()
            if txt:
                author_bio_parts.append(txt)
        elif isinstance(candidate, list):
            for entry in candidate:
                if isinstance(entry, str):
                    txt = entry.strip()
                elif isinstance(entry, dict):
                    txt = str(entry.get("authorInfo") or entry.get("info") or "").strip()
                else:
                    txt = ""
                if txt:
                    author_bio_parts.append(txt)

    review_parts: list[str] = []
    review_candidates = [
        aladin.get("reviewList"),
        sub_info.get("reviewList"),
        aladin.get("story"),
        sub_info.get("story"),
    ]
    for candidate in review_candidates:
        if isinstance(candidate, str):
            txt = candidate.strip()
            if txt:
                review_parts.append(txt)
            continue
        if not isinstance(candidate, list):
            continue
        for entry in candidate:
            if isinstance(entry, str):
                txt = entry.strip()
            elif isinstance(entry, dict):
                txt = " ".join(
                    t
                    for t in [
                        str(entry.get("reviewText") or "").strip(),
                        str(entry.get("story") or "").strip(),
                        str(entry.get("oneLineReview") or "").strip(),
                    ]
                    if t
                )
            else:
                txt = ""
            if txt:
                review_parts.append(txt)

    author_bio = clip(" ".join(author_bio_parts).strip(), MAX_CHARS_ALADIN_MEDIUM_TEXT)
    editorial_review = clip(" ".join(review_parts).strip(), MAX_CHARS_ALADIN_LONG_TEXT)
    # 서평/편집자 리뷰 필드가 비어 있어도, 알라딘은 책 소개(description)만 주는 경우가 많음.
    if not editorial_review:
        desc = str(aladin.get("description") or "").strip()
        editorial_review = clip(desc, MAX_CHARS_ALADIN_LONG_TEXT)
    return author_bio, editorial_review


async def _fetch_aladin_item(
    client: httpx.AsyncClient, api_key: str, isbn13: str
) -> tuple[dict, str | None]:
    """(item dict, 알라딘 오류 메시지 또는 None). HTTP 오류는 예외로 전달."""
    resp = await client.get(
        f"{ALADIN_BASE}/ItemLookUp.aspx",
        params={
            "ttbkey": api_key,
            "itemIdType": "ISBN13",
            "ItemId": isbn13,
            "output": "js",
            "Version": "20131101",
            "OptResult": "authorInfo,Toc,story,reviewList",
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        err = data.get("errorCode")
        if err is not None:
            msg = str(data.get("errorMessage") or data.get("message") or "알라딘 API 오류")
            return {}, f"code={err} {msg}"[:400]
    raw = data.get("item") if isinstance(data, dict) else None
    if isinstance(raw, dict):
        return raw, None
    if isinstance(raw, list) and raw:
        return (raw[0] if isinstance(raw[0], dict) else {}), None
    return {}, "item 없음(미등록 ISBN 또는 빈 응답)"


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _pick_primary_author(authors: str) -> str:
    s = (authors or "").strip()
    if not s:
        return ""
    for prefix in ["지은이:", "저자:", "글:", "저 :"]:
        if s.startswith(prefix):
            s = s[len(prefix) :].strip()
    for sep in [",", ";", "/", "&", "·"]:
        s = s.replace(sep, "|")
    first = s.split("|")[0].strip()
    for suffix in [" 지음", " 글", " 저", " 공저", " 편저"]:
        if first.endswith(suffix):
            first = first[: -len(suffix)].strip()
    return first


async def _fetch_wikipedia_bio(
    client: httpx.AsyncClient, author_name: str, user_agent: str
) -> tuple[str, str | None]:
    """(bio, error). ko 우선, 실패 시 en 재시도."""
    if not author_name:
        return "", "저자명 없음"

    async def _one_lang(lang: str) -> tuple[str, str | None]:
        try:
            search_resp = await client.get(
                WIKI_API_BASE.format(lang=lang),
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": author_name,
                    "srlimit": 1,
                    "format": "json",
                },
                headers={
                    "User-Agent": user_agent,
                    "Accept": "application/json",
                },
                timeout=15.0,
            )
            search_resp.raise_for_status()
            search_data = search_resp.json()
            hits = search_data.get("query", {}).get("search", [])
            if not hits:
                return "", f"{lang} 검색 결과 없음"
            title = str(hits[0].get("title") or "").strip()
            if not title:
                return "", f"{lang} 검색 title 없음"

            summary_resp = await client.get(
                WIKI_SUMMARY_BASE.format(lang=lang, title=quote(title, safe="")),
                headers={
                    "User-Agent": user_agent,
                    "Accept": "application/json",
                },
                timeout=15.0,
            )
            summary_resp.raise_for_status()
            summary_data = summary_resp.json()
            bio = str(summary_data.get("extract") or "").strip()
            if not bio:
                return "", f"{lang} summary extract 없음"
            return bio, None
        except Exception as e:
            return "", f"{lang} 위키 조회 실패: {e!s}"[:300]

    bio_ko, err_ko = await _one_lang("ko")
    if bio_ko:
        return bio_ko, None
    bio_en, err_en = await _one_lang("en")
    if bio_en:
        return bio_en, None
    return "", (err_ko or err_en or "위키 결과 없음")


def main() -> int:
    _load_env()

    ap = argparse.ArgumentParser(description="books.author_bio / books.editorial_review만 보강")
    ap.add_argument("--all", action="store_true", help="빈 값 여부와 무관하게 전체 책을 재조회")
    ap.add_argument("--limit", type=int, default=0, help="대상 책 수 제한 (0=제한 없음)")
    ap.add_argument("--concurrency", type=int, default=8, help="동시 조회 수")
    ap.add_argument("--dry-run", action="store_true", help="DB 업데이트 없이 조회 통계만 출력")
    ap.add_argument(
        "--wikipedia-author-bio",
        action="store_true",
        help="author_bio가 비면 Wikipedia(ko→en)로 보강",
    )
    ap.add_argument(
        "--wiki-only",
        action="store_true",
        help="알라딘 호출 없이 Wikipedia author_bio만 보강",
    )
    ap.add_argument(
        "--wiki-user-agent",
        default=(os.environ.get("WIKIPEDIA_USER_AGENT") or "").strip(),
        help="Wikipedia 요청 User-Agent (예: BookJukBookJukBot/1.0 (https://example.com; you@example.com))",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="처음 몇 건의 실패/빈 응답 사유를 stderr에 출력",
    )
    args = ap.parse_args()

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    aladin_key = (os.environ.get("ALADIN_API_KEY") or "").strip()
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY가 필요합니다.", file=sys.stderr)
        return 1
    if not args.wiki_only and not aladin_key:
        print("ALADIN_API_KEY가 필요합니다.", file=sys.stderr)
        return 1
    if args.wikipedia_author_bio and not args.wiki_user_agent:
        print(
            "--wikipedia-author-bio 사용 시 --wiki-user-agent 또는 WIKIPEDIA_USER_AGENT 설정이 필요합니다.",
            file=sys.stderr,
        )
        return 1

    try:
        from supabase import create_client
    except ImportError:
        print("pip install -r requirements.txt", file=sys.stderr)
        return 1

    client = create_client(url, key)
    try:
        rows = client.table("books").select("id,authors,author_bio,editorial_review").execute().data or []
    except Exception as e:
        print(f"books 조회 실패: {e}", file=sys.stderr)
        return 1

    targets: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if args.all or _is_blank(row.get("author_bio")) or _is_blank(row.get("editorial_review")):
            rid = str(row.get("id") or "").strip()
            if rid:
                targets.append({"id": rid, "authors": str(row.get("authors") or "")})

    if args.limit > 0:
        targets = targets[: args.limit]

    print(f"대상 책 수: {len(targets)} / 전체 {len(rows)}")
    if not targets:
        print("업데이트할 대상이 없습니다.")
        return 0

    async def run_async() -> tuple[list[dict], dict[str, int]]:
        sem = asyncio.Semaphore(max(1, args.concurrency))
        out: list[dict] = []
        stats: dict[str, int] = {
            "ok": 0,
            "http_or_parse_error": 0,
            "aladin_error_json": 0,
            "empty_item": 0,
            "both_fields_empty": 0,
            "wiki_filled": 0,
            "wiki_miss": 0,
            "wiki_error": 0,
        }
        verbose_samples = 5

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            async def one(book_id: str, authors: str) -> dict | None:
                nonlocal verbose_samples
                async with sem:
                    item: dict = {}
                    author_bio = ""
                    editorial_review = ""
                    if not args.wiki_only:
                        try:
                            item, aladin_note = await _fetch_aladin_item(http_client, aladin_key, book_id)
                        except Exception as e:
                            stats["http_or_parse_error"] += 1
                            if args.verbose and verbose_samples > 0:
                                print(f"  [실패] {book_id}: {e!s}"[:300], file=sys.stderr)
                                verbose_samples -= 1
                        else:
                            # 알라딘 JSON의 errorCode (note가 "code=..." 로 시작)
                            if aladin_note and aladin_note.startswith("code="):
                                stats["aladin_error_json"] += 1
                                if args.verbose and verbose_samples > 0:
                                    print(f"  [알라딘 오류] {book_id}: {aladin_note}", file=sys.stderr)
                                    verbose_samples -= 1
                            elif not item:
                                stats["empty_item"] += 1
                                if args.verbose and verbose_samples > 0:
                                    print(f"  [빈 item] {book_id}: {aladin_note or '응답 없음'}", file=sys.stderr)
                                    verbose_samples -= 1
                            else:
                                author_bio, editorial_review = _extract_author_bio_and_editorial_review(item)
                    if args.wikipedia_author_bio and not author_bio:
                        primary_author = _pick_primary_author(authors)
                        wiki_bio, wiki_err = await _fetch_wikipedia_bio(
                            http_client,
                            primary_author,
                            args.wiki_user_agent,
                        )
                        if wiki_bio:
                            author_bio = clip(wiki_bio, MAX_CHARS_ALADIN_MEDIUM_TEXT)
                            stats["wiki_filled"] += 1
                        else:
                            if wiki_err and "조회 실패" in wiki_err:
                                stats["wiki_error"] += 1
                            else:
                                stats["wiki_miss"] += 1
                            if args.verbose and verbose_samples > 0 and wiki_err:
                                print(f"  [위키] {book_id}/{primary_author}: {wiki_err}", file=sys.stderr)
                                verbose_samples -= 1
                    if args.wiki_only:
                        if not author_bio:
                            stats["both_fields_empty"] += 1
                            return None
                    elif not author_bio and not editorial_review:
                        stats["both_fields_empty"] += 1
                        return None
                    stats["ok"] += 1
                    return {
                        "id": book_id,
                        "author_bio": author_bio,
                        "editorial_review": editorial_review,
                    }

            results = await asyncio.gather(*[one(t["id"], t["authors"]) for t in targets])
            for r in results:
                if r:
                    out.append(r)
        return out, stats

    updates, stats = asyncio.run(run_async())
    print(f"API에서 값 확보: {len(updates)}권")
    print(
        "요약 - "
        f"성공(업서트 대상): {stats['ok']}, "
        f"HTTP/파싱 예외: {stats['http_or_parse_error']}, "
        f"알라딘 errorCode 응답: {stats['aladin_error_json']}, "
        f"item 비어 있음: {stats['empty_item']}, "
        f"추출 후 둘 다 빈 값: {stats['both_fields_empty']}, "
        f"위키 bio 보강 성공: {stats['wiki_filled']}, "
        f"위키 검색 미매치: {stats['wiki_miss']}, "
        f"위키 조회 오류: {stats['wiki_error']}"
    )
    if args.dry_run:
        print("Dry-run: DB 업데이트 없음.")
        return 0

    for i in range(0, len(updates), BATCH):
        chunk = updates[i : i + BATCH]
        try:
            client.table("books").upsert(chunk, on_conflict="id").execute()
        except Exception as e:
            print(f"업데이트 실패: {e}", file=sys.stderr)
            return 1
        print(f"Updated {min(i + len(chunk), len(updates))} / {len(updates)}")

    print("완료: author_bio / editorial_review 보강 업데이트")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
