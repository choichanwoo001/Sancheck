"""정보나루 loanItemSrch + 상세(srchDtlList, ISBN당 1회) + 알라딘으로 섹터(0~9)별 N권 수집 후 Supabase books 전체 교체.

  - 기존 Supabase `books` 행은 삭제 후 upsert (로컬 JSON은 수정하지 않음)
  - 어린이·교육용 제외: `book_catalog_filters.should_keep_book`
  - 시리즈물 제외(표제 키워드·만화로 보는·고믹·Why·권차·표제 내 총 N권 추정 등): `book_catalog_filters.explain_skip_series`

필요 환경 변수 (터미널에서 설정하거나 저장소 루트 `.env`):
  LIBRARY_API_KEY   — 정보나루 (필수)
  ALADIN_API_KEY    — 알라딘 TTB (필수, 설명·표지 등 품질·필터용)
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY

실행 (저장소 루트):
  pip install -r requirements.txt
  python backend/scripts/sync_supabase_books_from_api.py

옵션:
  --per-sector 50
  --dry-run       Supabase 쓰기 생략, 수집만 시험
  --max-pages 20  섹터당 loanItemSrch 최대 페이지(200권/페이지)
  --quiet-skips   건너뛴 도서(필터/누락) 로그 끄기 (기본: ISBN별 사유를 stderr에 출력)

문자열 길이:
  DB 저장 직전 상한은 `book_catalog_db_limits.py` — 알라딘 TTB 응답을 가능한 그대로 보존하고,
  비정상적으로 큰 페이로드만 차단한다. (설명·표지·출판일이 비는 주된 원인은 API 미제공이지 슬라이스가 아님.)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx

_SCRIPTS = Path(__file__).resolve().parent
REPO = _SCRIPTS.parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(REPO / "ai") not in sys.path:
    sys.path.insert(0, str(REPO / "ai"))

from book_catalog_db_limits import (  # noqa: E402
    MAX_CHARS_ALADIN_COVER_URL,
    MAX_CHARS_ALADIN_LONG_TEXT,
    MAX_CHARS_ALADIN_MEDIUM_TEXT,
    MAX_CHARS_ALADIN_PUB_DATE_RAW,
    MAX_CHARS_KDC_CLASS_NM,
    MAX_CHARS_KDC_CLASS_NO,
    MAX_CHARS_PUBLISHED_YEAR,
    MAX_CHARS_PUBLISHER,
    clip,
)
from _seed_common import get_supabase_credentials, load_repo_env, row_for_db, upsert_books  # noqa: E402
from book_catalog_filters import (  # noqa: E402
    explain_skip_content_filter,
    explain_skip_series,
)
from library_api import (  # noqa: E402
    BASE_URL,
    fetch_book_detail,
    _get_api_error_message,
)

ALADIN_BASE = "https://www.aladin.co.kr/ttb/api"
INTER_PAGE_SEC = 1.0
# 정보나루 srchDtlList: ISBN당 1회 호출 — 과도한 동시 요청 방지용(세마포어와 함께 사용)
LIBRARY_DELAY_SEC = 0.12
ALADIN_DELAY_SEC = 0.12

KDC_NAMES = {
    0: "총류",
    1: "철학",
    2: "종교",
    3: "사회과학",
    4: "자연과학",
    5: "기술과학",
    6: "예술",
    7: "언어",
    8: "문학",
    9: "역사",
}


def _log_skip(
    sector: int,
    isbn: str,
    reason: str,
    *,
    title_hint: str = "",
    quiet: bool = False,
) -> None:
    if quiet:
        return
    label = KDC_NAMES.get(sector, str(sector))
    hint = f' | "{title_hint[:40]}..."' if len(title_hint) > 40 else (f' | "{title_hint}"' if title_hint else "")
    print(f"  [건너뜀][{label}] ISBN {isbn} - {reason}{hint}", file=sys.stderr)


async def fetch_aladin_item(client: httpx.AsyncClient, api_key: str, isbn13: str) -> tuple[dict, str | None]:
    """알라딘 단권 조회. (item dict, 오류/빈 응답 설명) — 둘째가 None이면 정상."""
    if not api_key:
        return {}, "ALADIN_API_KEY 없음"
    try:
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
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("item")
        # TTB는 결과 1건일 때 item이 dict, 복수일 때 list로 올 수 있음 — 전부 빈 메타로
        # 저장되는 흔한 원인이 items[0]만 가정하는 것.
        if raw is None:
            return {}, "알라딘에 ISBN 미등록 또는 빈 응답"
        if isinstance(raw, dict):
            items = [raw]
        elif isinstance(raw, list):
            items = raw
        else:
            return {}, "알라딘 응답 item 형식 비정상"
        if not items:
            return {}, "알라딘에 ISBN 미등록 또는 빈 응답"
        return items[0], None
    except Exception as e:
        return {}, f"알라딘 API 오류: {e!s}"[:400]


def merge_library_aladin(
    sector: int,
    lib: dict,
    aladin: dict,
) -> tuple[dict | None, str | None]:
    """(행, None) 또는 (None, 건너뛴 이유)."""
    isbn = str(lib.get("isbn13") or "").strip()
    if not isbn:
        return None, "정보나루 상세에 ISBN 없음"
    title = (lib.get("title") or aladin.get("title") or "").strip()
    if not title:
        return None, "표제 없음 (정보나루·알라딘 모두)"
    title = clip(title, MAX_CHARS_ALADIN_MEDIUM_TEXT)

    authors = (lib.get("authors") or aladin.get("author", "") or "").strip()
    authors = clip(authors, MAX_CHARS_ALADIN_MEDIUM_TEXT)

    pub_lib = (lib.get("publisher") or "").strip()
    pub_ala = (aladin.get("publisher") or "").strip()
    publisher = clip(pub_lib or pub_ala, MAX_CHARS_PUBLISHER)

    # 알라딘 ItemLookUp: 책 소개 전문 (공개 스펙에 최대 길이 없음 → LONG_TEXT 로만 상한)
    description = clip((aladin.get("description") or "").strip(), MAX_CHARS_ALADIN_LONG_TEXT)

    sub_info = aladin.get("subInfo") if isinstance(aladin.get("subInfo"), dict) else {}

    # 알라딘 응답은 케이스에 따라 top-level / subInfo / 문자열·배열 형태가 섞여 온다.
    author_bio_parts: list[str] = []
    author_info_candidates = [
        aladin.get("authorInfo"),
        sub_info.get("authorInfo"),
        aladin.get("authorInfoAdd"),
        sub_info.get("authorInfoAdd"),
    ]
    for candidate in author_info_candidates:
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
    author_bio = clip(" ".join(author_bio_parts).strip(), MAX_CHARS_ALADIN_MEDIUM_TEXT)

    review_candidates = [
        aladin.get("reviewList"),
        sub_info.get("reviewList"),
        aladin.get("story"),
        sub_info.get("story"),
    ]
    review_parts: list[str] = []
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
                    t for t in [
                        str(entry.get("reviewText") or "").strip(),
                        str(entry.get("story") or "").strip(),
                        str(entry.get("oneLineReview") or "").strip(),
                    ] if t
                )
            else:
                txt = ""
            if txt:
                review_parts.append(txt)
    editorial_review = clip(" ".join(review_parts).strip(), MAX_CHARS_ALADIN_LONG_TEXT)

    # pubDate → DB에는 연도 4자리만 (손실 없이 일반적인 API 형식만 가정)
    pub_date_raw = clip(str(aladin.get("pubDate") or "").strip(), MAX_CHARS_ALADIN_PUB_DATE_RAW)
    published_year = pub_date_raw[:4] if pub_date_raw else ""

    cover = aladin.get("cover") or aladin.get("coverUrl") or ""
    if isinstance(cover, dict):
        cover = cover.get("url", "") or ""
    cover_url = clip(str(cover), MAX_CHARS_ALADIN_COVER_URL) if cover else ""

    return (
        {
            "id": isbn,
            "title": title,
            "authors": authors,
            "description": description,
            "author_bio": author_bio,
            "editorial_review": editorial_review,
            "publisher": publisher,
            "published_year": published_year,
            "kdc_class_no": clip(lib.get("class_no") or "", MAX_CHARS_KDC_CLASS_NO),
            "kdc_class_nm": clip(lib.get("class_nm") or "", MAX_CHARS_KDC_CLASS_NM),
            "sector": sector,
            "cover_image_url": cover_url,
        },
        None,
    )


async def fetch_loan_page(
    client: httpx.AsyncClient,
    auth_key: str,
    sector: int,
    page_no: int,
) -> list[str]:
    resp = await client.get(
        f"{BASE_URL}/loanItemSrch",
        params={
            "authKey": auth_key,
            "kdc": str(sector),
            "pageSize": "200",
            "pageNo": str(page_no),
            "format": "json",
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    data = resp.json()
    err = _get_api_error_message(data)
    if err:
        raise RuntimeError(err)
    docs = data.get("response", {}).get("docs", [])
    if isinstance(docs, dict):
        docs = [docs]
    isbns: list[str] = []
    for doc in docs:
        entry = doc.get("doc", doc)
        isbn = str(entry.get("isbn13") or entry.get("isbn") or "").strip()
        if isbn:
            isbns.append(isbn)
    return isbns


async def collect_sector(
    client: httpx.AsyncClient,
    library_key: str,
    aladin_key: str,
    sector: int,
    target: int,
    max_pages: int,
    seen_global: set[str],
    sem: asyncio.Semaphore,
    quiet_skips: bool,
) -> list[dict]:
    """섹터당 target권(필터 통과) 수집."""
    out: list[dict] = []
    page = 1
    while len(out) < target and page <= max_pages:
        try:
            isbns = await fetch_loan_page(client, library_key, sector, page)
        except Exception as e:
            print(f"  [섹터 {sector}] loanItemSrch 페이지 {page} 실패: {e}", file=sys.stderr)
            break
        if not isbns:
            break

        task_isbns = [i for i in isbns if i not in seen_global]
        if not task_isbns:
            page += 1
            await asyncio.sleep(INTER_PAGE_SEC)
            continue

        async def one(isbn: str) -> tuple[dict | None, str | None]:
            async with sem:
                await asyncio.sleep(LIBRARY_DELAY_SEC)
                try:
                    lib = await fetch_book_detail(client, library_key, isbn)
                except Exception as e:
                    return None, f"정보나루 상세(srchDtlList) 오류: {e!s}"[:220]
                await asyncio.sleep(ALADIN_DELAY_SEC)
                aladin, aladin_note = await fetch_aladin_item(client, aladin_key, isbn)
                row, merge_note = merge_library_aladin(sector, lib, aladin)
                if merge_note:
                    extra = f" ({aladin_note})" if aladin_note else ""
                    return None, merge_note + extra
                assert row is not None
                skip_c = explain_skip_content_filter(row)
                if skip_c:
                    return None, skip_c
                skip_s = explain_skip_series(aladin, row)
                if skip_s:
                    return None, skip_s
                return row, None

        results = await asyncio.gather(*[one(isbn) for isbn in task_isbns])
        for isbn, (r, skip_reason) in zip(task_isbns, results):
            if skip_reason is not None:
                _log_skip(sector, isbn, skip_reason, quiet=quiet_skips)
                continue
            if r is None:
                continue
            iid = str(r["id"])
            if iid in seen_global:
                continue
            seen_global.add(iid)
            out.append(r)
            tit = r["title"] or ""
            tshow = (tit[:42] + "...") if len(tit) > 42 else tit
            print(f"  [{KDC_NAMES.get(sector, sector)}] {len(out)}/{target} ISBN {iid} - {tshow}")
            if len(out) >= target:
                return out[:target]

        page += 1
        await asyncio.sleep(INTER_PAGE_SEC)

    return out


async def run_async(args: argparse.Namespace) -> list[dict]:
    library_key = (os.environ.get("LIBRARY_API_KEY") or "").strip()
    aladin_key = (os.environ.get("ALADIN_API_KEY") or "").strip()
    if not library_key:
        raise SystemExit("LIBRARY_API_KEY 가 필요합니다.")
    if not aladin_key:
        raise SystemExit("ALADIN_API_KEY 가 필요합니다 (설명·필터용).")

    all_rows: list[dict] = []
    seen: set[str] = set()
    sem = asyncio.Semaphore(6)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for sector in range(10):
            print(f"\n=== 섹터 {sector} ({KDC_NAMES[sector]}) - 목표 {args.per_sector}권 ===")
            rows = await collect_sector(
                client,
                library_key,
                aladin_key,
                sector,
                args.per_sector,
                args.max_pages,
                seen,
                sem,
                args.quiet_skips,
            )
            all_rows.extend(rows)
            if len(rows) < args.per_sector:
                print(
                    f"  [경고] 섹터 {sector}: 필터 후 {len(rows)}권만 확보 "
                    f"(목표 {args.per_sector}). 후보를 늘리려면 --max-pages 를 키우세요.",
                    file=sys.stderr,
                )
    return all_rows


def main() -> int:
    load_repo_env(REPO)
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="정보나루+알라딘으로 Supabase books 재구축")
    ap.add_argument("--per-sector", type=int, default=50, help="KDC 섹터(0~9)당 권수 (기본 50)")
    ap.add_argument("--max-pages", type=int, default=25, help="섹터당 loanItemSrch 최대 페이지")
    ap.add_argument("--dry-run", action="store_true", help="Supabase 삭제/upsert 생략")
    ap.add_argument(
        "--quiet-skips",
        action="store_true",
        help="건너뛴 도서(필터/누락) 로그 끄기 — 기본은 ISBN별 사유 출력",
    )
    args = ap.parse_args()

    url, key = get_supabase_credentials()
    if not args.dry_run and (not url or not key):
        print("SUPABASE_URL 과 SUPABASE_SERVICE_ROLE_KEY 가 필요합니다 (--dry-run 이면 생략 가능).", file=sys.stderr)
        return 1

    rows = asyncio.run(run_async(args))
    db_rows = [row_for_db(r) for r in rows]
    print(f"\n총 {len(db_rows)}권 수집 (섹터당 최대 {args.per_sector} 목표).")

    if args.dry_run:
        print("Dry-run: Supabase 반영 없음.")
        return 0

    try:
        from supabase import create_client
    except ImportError:
        print("pip install -r requirements.txt", file=sys.stderr)
        return 1

    client = create_client(url, key)
    print("Supabase books 기존 데이터 삭제 중...")
    try:
        client.table("books").delete().gte("sector", 0).execute()
    except Exception as e:
        print(f"Delete error: {e}", file=sys.stderr)
        return 1

    rc = upsert_books(client, db_rows, batch_size=500)
    if rc != 0:
        return rc

    print("완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
