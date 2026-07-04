"""Supabase `books` 점검: `book_catalog_filters`와 동일 기준으로 걸리는 행 삭제 후, 섹터별 부족분만 API로 다시 채움.

  - 콘텐츠 필터: DB 행만으로 판단 (`explain_skip_content_filter`)
  - 시리즈 필터: DB의 **표제(title)** 만으로 `explain_skip_series` + 전역 `map_ids_to_similar_title_cluster_skip` (LCS≥50% 연결 3권 이상)

필요 환경 변수:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
  보충 시: LIBRARY_API_KEY, ALADIN_API_KEY

실행 (저장소 루트):
  python backend/scripts/prune_and_refill_supabase_books.py
  python backend/scripts/prune_and_refill_supabase_books.py --dry-run
  python backend/scripts/prune_and_refill_supabase_books.py --prune-only

옵션:
  --per-sector 50   섹터(0~9)당 목표 권수 (보충 상한)
  --max-pages 25    보충 시 loanItemSrch 최대 페이지
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import httpx

_SCRIPTS = Path(__file__).resolve().parent
REPO = _SCRIPTS.parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(REPO / "ai") not in sys.path:
    sys.path.insert(0, str(REPO / "ai"))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

import sync_supabase_books_from_api as book_sync  # noqa: E402

from book_catalog_filters import (  # noqa: E402
    explain_skip_content_filter,
    explain_skip_series,
    map_ids_to_similar_title_cluster_skip,
)


def _load_env() -> None:
    if not load_dotenv:
        return
    p = REPO / ".env"
    if p.is_file():
        load_dotenv(p)


def _db_row_to_filter_row(r: dict) -> dict:
    """merge_library_aladin 결과와 동일 키로 필터에 넘길 dict."""
    try:
        sector = int(r.get("sector") or 0)
    except (TypeError, ValueError):
        sector = 0
    return {
        "id": str(r.get("id") or ""),
        "title": str(r.get("title") or ""),
        "authors": str(r.get("authors") or ""),
        "description": str(r.get("description") or ""),
        "publisher": str(r.get("publisher") or ""),
        "kdc_class_nm": str(r.get("kdc_class_nm") or ""),
        "sector": sector,
    }


def fetch_all_books_sb(sb, page_size: int = 1000) -> list[dict]:
    """Supabase books 전체 (페이지네이션)."""
    out: list[dict] = []
    start = 0
    while True:
        q = (
            sb.table("books")
            .select("*")
            .order("id")
            .range(start, start + page_size - 1)
        )
        resp = q.execute()
        batch = resp.data or []
        if not batch:
            break
        out.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return out


def delete_books_by_ids(sb, ids: list[str], chunk_size: int = 150) -> None:
    if not ids:
        return
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        sb.table("books").delete().in_("id", chunk).execute()


def audit_rows(rows: list[dict]) -> tuple[list[str], Counter[str]]:
    """삭제할 id 목록과 사유별 건수. 시리즈는 표제만 사용 (`explain_skip_series`) + 유사 표제 군집."""
    cluster_skip = map_ids_to_similar_title_cluster_skip(rows)
    to_delete: list[str] = []
    reasons: Counter[str] = Counter()

    for r in rows:
        row = _db_row_to_filter_row(r)
        bid = row["id"]
        if not bid:
            continue

        c = explain_skip_content_filter(row)
        if c:
            to_delete.append(bid)
            reasons[c] += 1
            continue

        s = explain_skip_series({}, row)
        if s:
            to_delete.append(bid)
            reasons[s] += 1
            continue

        sc = cluster_skip.get(bid)
        if sc:
            to_delete.append(bid)
            reasons[sc] += 1

    return to_delete, reasons


def sector_counts(rows: list[dict]) -> dict[int, int]:
    c: dict[int, int] = defaultdict(int)
    for r in rows:
        try:
            s = int(r.get("sector") or 0)
        except (TypeError, ValueError):
            s = 0
        if 0 <= s <= 9:
            c[s] += 1
    return dict(c)


async def refill_sectors(
    args: argparse.Namespace,
    library_key: str,
    aladin_key: str,
    seen: set[str],
    needed: dict[int, int],
) -> list[dict]:
    """needed[sector] > 0 인 섹터만 collect_sector 호출."""
    collected: list[dict] = []
    sem = asyncio.Semaphore(6)
    async with httpx.AsyncClient(timeout=30.0) as http:
        for sector in range(10):
            n = needed.get(sector, 0)
            if n <= 0:
                continue
            print(f"\n=== 보충 섹터 {sector} ({book_sync.KDC_NAMES[sector]}) — {n}권 ===")
            rows = await book_sync.collect_sector(
                http,
                library_key,
                aladin_key,
                sector,
                n,
                args.max_pages,
                seen,
                sem,
                args.quiet_skips,
            )
            collected.extend(rows)
            if len(rows) < n:
                print(
                    f"  [경고] 섹터 {sector}: {len(rows)}권만 확보 (목표 {n}). "
                    f"--max-pages 를 늘려 보세요.",
                    file=sys.stderr,
                )
    return collected


async def run_async(args: argparse.Namespace) -> int:
    _load_env()
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    library_key = (os.environ.get("LIBRARY_API_KEY") or "").strip()
    aladin_key = (os.environ.get("ALADIN_API_KEY") or "").strip()

    if not url or not key:
        print("SUPABASE_URL 과 SUPABASE_SERVICE_ROLE_KEY 가 필요합니다.", file=sys.stderr)
        return 1

    try:
        from supabase import create_client
    except ImportError:
        print("pip install supabase", file=sys.stderr)
        return 1

    sb = create_client(url, key)
    print("Supabase books 전체 로드 중...")
    initial = fetch_all_books_sb(sb)
    print(f"  현재 {len(initial)}권")

    to_delete, reason_counts = audit_rows(initial)

    to_delete = list(dict.fromkeys(to_delete))
    print(f"\n필터 위반으로 삭제 대상: {len(to_delete)}권")
    for reason, cnt in reason_counts.most_common():
        print(f"  - {cnt:4d}  {reason}")

    if args.dry_run:
        print("\n[--dry-run] DB 삭제·보충 없음.")
        return 0

    if to_delete:
        print("\n삭제 실행 중...")
        delete_books_by_ids(sb, to_delete)
        print(f"  삭제 완료 ({len(to_delete)}권)")

    if args.prune_only:
        print("\n[--prune-only] 보충 생략.")
        return 0

    if not library_key:
        print("LIBRARY_API_KEY 가 필요합니다 (보충 수집).", file=sys.stderr)
        return 1
    if not aladin_key:
        print("ALADIN_API_KEY 가 필요합니다 (보충 수집).", file=sys.stderr)
        return 1

    remaining = fetch_all_books_sb(sb)
    counts = sector_counts(remaining)
    seen: set[str] = {str(r.get("id") or "") for r in remaining if r.get("id")}

    needed: dict[int, int] = {}
    for s in range(10):
        have = counts.get(s, 0)
        lack = args.per_sector - have
        if lack > 0:
            needed[s] = lack

    total_need = sum(needed.values())
    if total_need == 0:
        print("\n섹터별 권수가 이미 목표 이상이라 보충 없음.")
        return 0

    print(f"\n보충 필요 합계 {total_need}권 (섹터별 목표 {args.per_sector}):")
    for s in range(10):
        if needed.get(s):
            print(f"  섹터 {s} ({book_sync.KDC_NAMES[s]}): +{needed[s]}권")

    new_rows = await refill_sectors(args, library_key, aladin_key, seen, needed)
    if not new_rows:
        print("\n새로 수집된 행 없음.")
        return 0

    db_rows = [book_sync.row_for_db(r) for r in new_rows]
    for i in range(0, len(db_rows), book_sync.BATCH):
        chunk = db_rows[i : i + book_sync.BATCH]
        sb.table("books").upsert(chunk, on_conflict="id").execute()
        print(f"Upsert {min(i + len(chunk), len(db_rows))} / {len(db_rows)}")

    print("\n완료.")
    return 0


def main() -> int:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Supabase books 필터 점검·삭제·부족분 보충")
    ap.add_argument("--per-sector", type=int, default=50, help="섹터당 목표 권수 (기본 50)")
    ap.add_argument("--max-pages", type=int, default=25, help="보충 시 loanItemSrch 최대 페이지")
    ap.add_argument("--dry-run", action="store_true", help="삭제·보충 없이 점검만")
    ap.add_argument("--prune-only", action="store_true", help="삭제만 하고 보충 안 함")
    ap.add_argument("--quiet-skips", action="store_true", help="보충 수집 시 건너뜀 로그 끄기")
    args = ap.parse_args()

    return asyncio.run(run_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
