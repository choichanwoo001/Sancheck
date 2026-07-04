"""BookVectorStore ↔ Supabase `public.book_vectors` (임베딩 upsert / 로드).

`HYBRID_PERSIST_EMBEDDINGS` 가 켜져 있으면(기본: `HYBRID_PERSIST_KG` 와 동일) 등록 시 자동 upsert.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .phase2_model.vector_store import BookVector, BookVectorStore

_MAX_ISBN = 20
_MAX_TITLE = 300
_MAX_AUTHORS = 500
_MAX_KDC = 50


def _clip(s: str, n: int) -> str:
    t = (s or "").strip()
    return t[:n] if len(t) > n else t


def book_vector_to_row(bv: BookVector) -> dict[str, Any]:
    """DB 행 dict (varchar 길이 제한)."""
    return {
        "isbn": _clip(bv.isbn13, _MAX_ISBN),
        "title": _clip(bv.title, _MAX_TITLE) or "(제목 없음)",
        "authors": _clip(bv.authors, _MAX_AUTHORS),
        "vector": bv.vector.astype(float).tolist(),
        "kdc_class": _clip(bv.kdc_class, _MAX_KDC),
        "is_cold_start": bool(bv.is_cold_start),
    }


def upsert_book_vector(supabase: Any, bv: BookVector) -> None:
    """ISBN 기준 upsert (`book_vectors_isbn_unique`)."""
    if supabase is None:
        return
    isbn = _clip(bv.isbn13, _MAX_ISBN)
    if not isbn:
        print("[WARN] book_vectors upsert 생략: isbn 비어 있음")
        return
    row = book_vector_to_row(bv)
    try:
        supabase.table("book_vectors").upsert(
            row,
            on_conflict="isbn",
        ).execute()
    except Exception as e:
        print(f"[WARN] book_vectors upsert 실패 ({isbn}): {e}")


_BATCH = 200


def upsert_all_book_vectors(supabase: Any, store: BookVectorStore) -> None:
    """메모리에 있는 모든 책 벡터를 DB에 반영한다."""
    if supabase is None or len(store) == 0:
        return
    rows = [book_vector_to_row(bv) for bv in store._books if _clip(bv.isbn13, _MAX_ISBN)]
    if not rows:
        return
    ok_rows = 0
    for i in range(0, len(rows), _BATCH):
        chunk = rows[i : i + _BATCH]
        try:
            supabase.table("book_vectors").upsert(
                chunk, on_conflict="isbn"
            ).execute()
            ok_rows += len(chunk)
        except Exception as e:
            print(f"[WARN] book_vectors 배치 upsert 실패: {e}")
    if ok_rows > 0:
        print(f"[Vector] Supabase upsert 완료: {ok_rows}권")
    else:
        print(
            f"[오류] book_vectors upsert가 모두 실패했습니다 ({len(rows)}권 시도). "
            "DB에 `book_vectors(isbn)` 비부분 유니크 인덱스가 있는지 마이그레이션 "
            "`20260425120000_bookjuk_full_schema.sql`(book_vectors isbn 유니크) 적용 여부를 확인하세요."
        )


def load_book_vectors_from_supabase(supabase: Any) -> list[BookVector]:
    """`book_vectors` 전체를 읽어 BookVector 목록으로 반환."""
    if supabase is None:
        return []
    try:
        res = supabase.table("book_vectors").select(
            "isbn,title,authors,vector,kdc_class,is_cold_start"
        ).execute()
    except Exception as e:
        print(f"[WARN] book_vectors 조회 실패: {e}")
        return []

    rows = getattr(res, "data", None) or []
    out: list[BookVector] = []
    for row in rows:
        raw_isbn = row.get("isbn")
        isbn = str(raw_isbn).strip() if raw_isbn is not None else ""
        if not isbn:
            continue
        vec_raw = row.get("vector")
        if vec_raw is None:
            continue
        if isinstance(vec_raw, str):
            import json

            try:
                vec_raw = json.loads(vec_raw)
            except json.JSONDecodeError:
                continue
        if not isinstance(vec_raw, list):
            continue
        vec = np.asarray(vec_raw, dtype=np.float64)
        if vec.size == 0:
            continue
        out.append(
            BookVector(
                isbn13=isbn,
                title=str(row.get("title") or "").strip() or isbn,
                authors=str(row.get("authors") or "").strip(),
                vector=vec,
                kdc_class=str(row.get("kdc_class") or "").strip(),
                is_cold_start=bool(row.get("is_cold_start")),
            )
        )
    return out
