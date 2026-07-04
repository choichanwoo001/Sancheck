"""Supabase에 하이브리드 추천용 KG(`kg_nodes`/`kg_edges`)·`book_vectors`를 구축한다.

기본: **사용자 이력**(ratings / shelves / book_user_states)에 나온 책 ISBN만 `add_books` 한다.
`public.books` 에 해당 행이 있어야 한다 — 없으면 먼저:

  python backend/scripts/seed_hybrid_recommender_e2e.py --isbn ...

환경 (루트 `.env`):
  OPENAI_API_KEY
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (서비스 롤 권장)
  HYBRID_USE_SUPABASE=1
  HYBRID_PERSIST_KG=1

실행 (`ai` 디렉터리) — 사용자 기본값은 `hybrid_recommender_main.py` 와 동일 (`dev_test_user_1` 등):

  python build_hybrid_catalog.py

  python build_hybrid_catalog.py --supabase-user-id <users.Key>

수동으로 ISBN만 지정할 때(이력과 무관):

  python build_hybrid_catalog.py --isbn 9788937460470 9788936434120

`books` 테이블에 많이 있고 `book_vectors`에만 없는 나머지를 한꺼번에 넣을 때:

  python build_hybrid_catalog_bulk.py
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
from hybrid_recommender.supabase_user_profile import load_user_profile_from_supabase

# hybrid_recommender_main.py 와 동일
DEFAULT_SUPABASE_USER_ID = "dev_test_user_1"


def _exit(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _resolve_supabase_user_id(cli_value: str | None) -> str:
    if cli_value and str(cli_value).strip():
        return str(cli_value).strip()
    env_uid = os.getenv("HYBRID_CLI_SUPABASE_USER_ID", "").strip()
    if env_uid:
        return env_uid
    return DEFAULT_SUPABASE_USER_ID


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="사용자 DB 이력(또는 --isbn) 기준으로 하이브리드 KG·임베딩을 Supabase에 구축",
    )
    parser.add_argument(
        "--supabase-user-id",
        metavar="USER_KEY",
        default=None,
        help="이력에서 ISBN을 모을 사용자 (생략 시 HYBRID_CLI_SUPABASE_USER_ID, 없으면 dev_test_user_1). --isbn 있으면 무시",
    )
    parser.add_argument(
        "--isbn",
        nargs="+",
        metavar="ISBN",
        default=None,
        help="지정 시 이 목록만 구축(이력 기반 대신 사용)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="병렬 API 호출 수 (기본 3)",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        _exit("[오류] OPENAI_API_KEY 가 필요합니다.")

    pipeline = HybridRecommenderPipeline.from_env(
        user_id="catalog_build",
    )
    if not pipeline.supabase_client:
        _exit("[오류] Supabase 클라이언트가 없습니다. SUPABASE_URL·키·HYBRID_USE_SUPABASE 를 확인하세요.")
    if not pipeline.persist_kg:
        _exit("[오류] KG DB 영속이 꺼져 있습니다. HYBRID_PERSIST_KG=1 을 설정하세요.")
    if not pipeline.persist_embeddings:
        print("[안내] HYBRID_PERSIST_EMBEDDINGS 가 꺼져 있어 book_vectors 는 저장되지 않을 수 있습니다.")

    sb = pipeline.supabase_client

    if args.isbn:
        isbns = [x.strip() for x in args.isbn if x.strip()]
        print(f"[구축] --isbn 지정: {len(isbns)}권 (이력 무시)")
    else:
        uid = _resolve_supabase_user_id(args.supabase_user_id)
        print(f"[구축] 사용자 이력 기준: {uid}")
        profile = load_user_profile_from_supabase(sb, uid)
        isbns = profile.distinct_isbn13s()
        if not isbns:
            _exit(
                "[오류] 이 사용자에 대한 이력(ratings / shelves / book_user_states)에 책이 없습니다. "
                "시드하거나 --isbn 으로 ISBN을 직접 지정하세요."
            )
        print(f"  이력에서 수집한 서로 다른 ISBN: {len(isbns)}권")

    print(
        f"[구축] KG·벡터 (persist_kg={pipeline.persist_kg}, persist_emb={pipeline.persist_embeddings})"
    )
    await pipeline.add_books(isbn_list=isbns, concurrency=args.concurrency)
    print("[완료] 이제 `python hybrid_recommender_main.py` 로 추천을 실행할 수 있습니다.")


if __name__ == "__main__":
    asyncio.run(_main())
