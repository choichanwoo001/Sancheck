from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from book_catalog_db_limits import (
    MAX_CHARS_ALADIN_COVER_URL,
    MAX_CHARS_ALADIN_LONG_TEXT,
    MAX_CHARS_ALADIN_MEDIUM_TEXT,
    MAX_CHARS_KDC_CLASS_NM,
    MAX_CHARS_KDC_CLASS_NO,
    MAX_CHARS_PUBLISHED_YEAR,
    MAX_CHARS_PUBLISHER,
    clip,
)


def load_repo_env(repo: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = repo / ".env"
    if env_path.is_file():
        load_dotenv(env_path)


def row_for_db(obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(obj.get("id", "")),
        "title": clip(obj.get("title"), MAX_CHARS_ALADIN_MEDIUM_TEXT),
        "authors": clip(obj.get("authors"), MAX_CHARS_ALADIN_MEDIUM_TEXT),
        "description": clip(obj.get("description"), MAX_CHARS_ALADIN_LONG_TEXT),
        "author_bio": clip(obj.get("author_bio"), MAX_CHARS_ALADIN_MEDIUM_TEXT),
        "editorial_review": clip(obj.get("editorial_review"), MAX_CHARS_ALADIN_LONG_TEXT),
        "publisher": clip(obj.get("publisher"), MAX_CHARS_PUBLISHER),
        "published_year": clip(str(obj.get("published_year") or ""), MAX_CHARS_PUBLISHED_YEAR),
        "kdc_class_no": clip(obj.get("kdc_class_no"), MAX_CHARS_KDC_CLASS_NO),
        "kdc_class_nm": clip(obj.get("kdc_class_nm"), MAX_CHARS_KDC_CLASS_NM),
        "sector": int(obj.get("sector") or 0),
        "cover_image_url": clip(obj.get("cover_image_url"), MAX_CHARS_ALADIN_COVER_URL),
    }


def get_supabase_credentials() -> tuple[str, str]:
    return (os.environ.get("SUPABASE_URL") or "").strip(), (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()


def create_supabase_client() -> Any:
    try:
        from supabase import create_client
    except ImportError:
        print("Install: pip install -r requirements.txt", file=sys.stderr)
        raise SystemExit(1)
    url, key = get_supabase_credentials()
    if not url or not key:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment.", file=sys.stderr)
        raise SystemExit(1)
    return create_client(url, key)


def upsert_books(client: Any, rows: list[dict[str, Any]], batch_size: int = 500) -> int:
    for index in range(0, len(rows), batch_size):
        chunk = rows[index : index + batch_size]
        try:
            client.table("books").upsert(chunk, on_conflict="id").execute()
        except Exception as exc:
            print(f"Upsert error: {exc}", file=sys.stderr)
            return 1
        print(f"Upserted {min(index + len(chunk), len(rows))} / {len(rows)}")
    return 0
