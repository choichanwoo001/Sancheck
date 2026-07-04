"""booksCatalog.json(또는 export 스크립트 결과)을 Supabase public.books 에 upsert 합니다.

사전 준비:
  pip install -r requirements.txt

환경 변수 (터미널에 직접 설정하거나, 다른 스크립트와 같이 저장소 루트 `.env`에 두는 방식):
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY  (anon 키가 아님 — 서버/로컬 시드 전용)

실행 (저장소 루트에서):
  python backend/scripts/seed_supabase_books.py
  python backend/scripts/seed_supabase_books.py path/to/custom.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _seed_common import create_supabase_client, load_repo_env, row_for_db, upsert_books

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_JSON = REPO / "frontend" / "src" / "data" / "booksCatalog.json"


def main() -> int:
    load_repo_env(REPO)

    json_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_JSON
    if not json_path.is_file():
        print(f"Missing file: {json_path}", file=sys.stderr)
        return 1

    with open(json_path, encoding="utf-8") as f:
        rows_in = json.load(f)
    if not isinstance(rows_in, list):
        print("JSON must be an array of book objects.", file=sys.stderr)
        return 1

    rows = [row_for_db(r) for r in rows_in if r.get("id")]
    client = create_supabase_client()
    rc = upsert_books(client, rows, batch_size=500)
    if rc != 0:
        return rc

    print(f"Done. Total {len(rows)} books from {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
