"""Supabase `public.books` → frontend/src/data/booksCatalog.json

로컬 SQLite 없이 원격 카탈로그만 사용할 때 폴백 JSON을 갱신합니다.

환경 변수 (저장소 루트 `.env` 등):
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
OUT_PATH = _REPO / "frontend" / "src" / "data" / "booksCatalog.json"

_SELECT = (
    "id,title,authors,description,author_bio,editorial_review,"
    "publisher,published_year,kdc_class_no,kdc_class_nm,sector,cover_image_url"
)


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None

    if load_dotenv:
        p = _REPO / ".env"
        if p.is_file():
            load_dotenv(p)

    try:
        from supabase import create_client
    except ImportError:
        print("Install: pip install supabase", file=sys.stderr)
        return 1

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.", file=sys.stderr)
        return 1

    client = create_client(url, key)
    try:
        resp = client.table("books").select(_SELECT).order("id").execute()
    except Exception as e:
        print(f"Query error: {e}", file=sys.stderr)
        return 1

    raw = getattr(resp, "data", None) or []
    rows = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        rows.append(
            {
                "id": str(r.get("id") or ""),
                "title": r.get("title") or "",
                "authors": r.get("authors") or "",
                "description": r.get("description") or "",
                "author_bio": r.get("author_bio") or "",
                "editorial_review": r.get("editorial_review") or "",
                "publisher": r.get("publisher") or "",
                "published_year": str(r.get("published_year") or ""),
                "kdc_class_no": r.get("kdc_class_no") or "",
                "kdc_class_nm": r.get("kdc_class_nm") or "",
                "sector": int(r.get("sector") or 0),
                "cover_image_url": r.get("cover_image_url") or "",
            }
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with_cover = sum(1 for r in rows if r.get("cover_image_url"))
    print(f"Wrote {len(rows)} books ({with_cover} with cover) -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
