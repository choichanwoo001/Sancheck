"""Supabase `public.books`에 있는 ISBN 중, 아직 `book_vectors`에 없는 책만 골라 KG·임베딩을 구축한다.

`build_hybrid_catalog.py`는 사용자 이력 ISBN 또는 수동 `--isbn`만 처리한다.
이 스크립트는 **DB 전체 카탈로그**에서 남은 권을 배치로 넣을 때 쓴다.

선행 조건:
  - `books` 테이블에 해당 ISBN 행이 이미 있어야 `add_books`가 메타를 Supabase에서 읽을 수 있다.
    (없으면 `backend/scripts/seed_supabase_books.py` 등으로 먼저 채움)

환경 (저장소 루트 `.env`):
  OPENAI_API_KEY
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
  HYBRID_USE_SUPABASE=1, HYBRID_PERSIST_KG=1, HYBRID_PERSIST_EMBEDDINGS=1

실행 (`ai` 디렉터리):

  # book_vectors에 없는 책 중 최대 500권만 (기본)
  python build_hybrid_catalog_bulk.py

  # 남은 전부 한 번에
  python build_hybrid_catalog_bulk.py --max 0

  # 이미 벡터가 있어도 다시 돌리기(재임베딩·KG 갱신)
  python build_hybrid_catalog_bulk.py --max 100 --include-vectorized

  # 목록만 보기
  python build_hybrid_catalog_bulk.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_AI_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _AI_DIR.parent
if (_REPO_ROOT / ".env").is_file():
    load_dotenv(_REPO_ROOT / ".env")

sys.path.insert(0, str(_AI_DIR))

from hybrid_recommender import HybridRecommenderPipeline


def _exit(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _fetch_all_book_ids(sb, page_size: int = 1000) -> list[str]:
    """public.books.id(ISBN) 전부."""
    out: list[str] = []
    start = 0
    while True:
        end = start + page_size - 1
        res = (
            sb.table("books")
            .select("id")
            .order("id")
            .range(start, end)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        if not rows:
            break
        for row in rows:
            rid = row.get("id")
            if rid is not None:
                s = str(rid).strip()
                if s:
                    out.append(s)
        if len(rows) < page_size:
            break
        start += page_size
    return out


def _fetch_vector_isbns(sb, page_size: int = 1000) -> set[str]:
    """book_vectors에 이미 있는 ISBN."""
    s: set[str] = set()
    start = 0
    while True:
        end = start + page_size - 1
        res = (
            sb.table("book_vectors")
            .select("isbn")
            .order("isbn")
            .range(start, end)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        if not rows:
            break
        for row in rows:
            raw = row.get("isbn")
            if raw is not None:
                t = str(raw).strip()
                if t:
                    s.add(t)
        if len(rows) < page_size:
            break
        start += page_size
    return s


async def _main() -> None:
    ap = argparse.ArgumentParser(
        description="Supabase books 전체 중 아직 book_vectors에 없는 ISBN만 KG·벡터 구축",
    )
    ap.add_argument(
        "--max",
        type=int,
        default=500,
        metavar="N",
        help="이번 실행에서 처리할 권 수 상한 (기본 500). 0이면 남은 전부",
    )
    ap.add_argument(
        "--offset",
        type=int,
        default=0,
        help="남은 목록 정렬 후 앞에서 건너뛸 개수 (배치 나눠 돌릴 때)",
    )
    ap.add_argument(
        "--include-vectorized",
        action="store_true",
        help="book_vectors에 이미 있는 ISBN도 포함(재구축). 기본은 미포함",
    )
    ap.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="add_books 병렬 수 (기본 3)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="ISBN만 조회·집계하고 add_books는 하지 않음",
    )
    args = ap.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        _exit("[오류] OPENAI_API_KEY 가 필요합니다.")

    pipeline = HybridRecommenderPipeline.from_env(user_id="catalog_build_bulk")
    if not pipeline.supabase_client:
        _exit("[오류] Supabase 클라이언트가 없습니다. SUPABASE_URL·키·HYBRID_USE_SUPABASE 를 확인하세요.")
    if not pipeline.persist_kg:
        _exit("[오류] HYBRID_PERSIST_KG=1 을 설정하세요.")
    if not pipeline.persist_embeddings:
        print("[안내] HYBRID_PERSIST_EMBEDDINGS 가 꺼져 있으면 book_vectors에 저장되지 않습니다.")

    sb = pipeline.supabase_client

    print("[조회] public.books ISBN 목록 로드 중…")
    all_ids = _fetch_all_book_ids(sb)
    print(f"       books 행: {len(all_ids)}권")

    if not args.include_vectorized:
        print("[조회] book_vectors에 있는 ISBN 로드 중…")
        have_vec = _fetch_vector_isbns(sb)
        print(f"       book_vectors: {len(have_vec)}권")
        remaining = [x for x in all_ids if x not in have_vec]
    else:
        have_vec = set()
        remaining = list(all_ids)

    remaining.sort()
    print(f"[집계] 처리 대상(정렬 후): {len(remaining)}권")

    if args.offset:
        if args.offset >= len(remaining):
            print(f"[안내] --offset {args.offset} >= 남은 권수 {len(remaining)} → 할 일 없음")
            return
        remaining = remaining[args.offset :]

    max_n = args.max
    if max_n and max_n > 0:
        batch = remaining[:max_n]
    else:
        batch = remaining

    print(f"[실행] 이번에 add_books 할 ISBN: {len(batch)}권 (offset={args.offset}, max={max_n})")

    if args.dry_run:
        for i, isbn in enumerate(batch[:20]):
            print(f"  {i + 1}. {isbn}")
        if len(batch) > 20:
            print(f"  … 외 {len(batch) - 20}권")
        print("[dry-run] 종료 (실제 구축 없음)")
        return

    if not batch:
        print("[안내] add_books 할 ISBN이 없습니다. books를 채우거나 --include-vectorized 를 검토하세요.")
        return

    print(
        f"[구축] KG·벡터 (persist_kg={pipeline.persist_kg}, "
        f"persist_emb={pipeline.persist_embeddings})"
    )
    await pipeline.add_books(isbn_list=batch, concurrency=args.concurrency)
    print("[완료] `python hybrid_recommender_main.py` 로 추천을 확인할 수 있습니다.")


if __name__ == "__main__":
    asyncio.run(_main())
