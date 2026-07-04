"""정보나루(data4library.kr) API — 도서 상세·키워드·배치 조회.

이전 위치: `ai/taste_analysis/library_api.py` (레거시 클러스터링 파이프라인과 분리).
"""
import asyncio
import os
import random
from dataclasses import dataclass

import httpx

BASE_URL = "http://data4library.kr/api"

KDC_CATEGORIES = [
    ("0", "총류"),
    ("1", "철학"),
    ("2", "종교"),
    ("3", "사회과학"),
    ("4", "자연과학"),
    ("5", "기술과학"),
    ("6", "예술"),
    ("7", "언어"),
    ("8", "문학"),
    ("9", "역사"),
]


@dataclass
class BookKeyword:
    word: str
    weight: float


@dataclass
class BookInfo:
    isbn13: str
    title: str
    authors: str
    publisher: str
    class_no: str
    class_nm: str
    keywords: list[BookKeyword]


async def fetch_keywords(
    client: httpx.AsyncClient,
    auth_key: str,
    isbn13: str,
) -> list[BookKeyword]:
    resp = await client.get(
        f"{BASE_URL}/keywordList",
        params={
            "authKey": auth_key,
            "isbn13": isbn13,
            "additionalYN": "N",
            "format": "json",
        },
    )
    resp.raise_for_status()
    data = resp.json()

    keywords: list[BookKeyword] = []
    items = data.get("response", {}).get("items", [])
    if isinstance(items, list):
        for item in items:
            entry = item.get("item", item)
            keywords.append(
                BookKeyword(
                    word=entry["word"],
                    weight=float(entry["weight"]),
                )
            )
    return keywords


async def fetch_book_detail(
    client: httpx.AsyncClient,
    auth_key: str,
    isbn13: str,
) -> dict:
    resp = await client.get(
        f"{BASE_URL}/srchDtlList",
        params={
            "authKey": auth_key,
            "isbn13": isbn13,
            "format": "json",
        },
    )
    resp.raise_for_status()
    data = resp.json()

    detail = data.get("response", {}).get("detail", [])
    if detail:
        book = detail[0].get("book", {})
        return {
            "isbn13": isbn13,
            "title": book.get("bookname", ""),
            "authors": book.get("authors", ""),
            "publisher": book.get("publisher", ""),
            "class_no": book.get("class_no", ""),
            "class_nm": book.get("class_nm", ""),
        }
    return {
        "isbn13": isbn13,
        "title": "",
        "authors": "",
        "publisher": "",
        "class_no": "",
        "class_nm": "",
    }


# 배치 조회 시 한 번에 넣을 ISBN 개수 (정보나루 공식 문서에 복수 ISBN 한도 미명시, recommandList는 세미콜론 복수 지원)
DETAIL_BATCH_SIZE = 50


async def fetch_book_details_batch(
    client: httpx.AsyncClient,
    auth_key: str,
    isbn_list: list[str],
) -> list[dict]:
    """여러 ISBN의 도서 상세를 한 번의 srchDtlList 호출로 조회. 실패 시 빈 리스트."""
    if not isbn_list:
        return []
    isbn_param = ";".join(isbn_list)
    try:
        resp = await client.get(
            f"{BASE_URL}/srchDtlList",
            params={
                "authKey": auth_key,
                "isbn13": isbn_param,
                "format": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    if _get_api_error_message(data):
        return []

    detail = data.get("response", {}).get("detail", [])
    if isinstance(detail, dict):
        detail = [detail]
    if not detail:
        return []

    result: list[dict] = []
    for i, d in enumerate(detail):
        book = d.get("book", d)
        isbn13 = isbn_list[i] if i < len(isbn_list) else book.get("isbn13", "")
        result.append({
            "isbn13": isbn13,
            "title": book.get("bookname", ""),
            "authors": book.get("authors", ""),
            "publisher": book.get("publisher", ""),
            "class_no": book.get("class_no", ""),
            "class_nm": book.get("class_nm", ""),
        })
    return result


async def _fetch_single_book(
    client: httpx.AsyncClient,
    auth_key: str,
    isbn13: str,
) -> BookInfo:
    keywords, detail = await asyncio.gather(
        fetch_keywords(client, auth_key, isbn13),
        fetch_book_detail(client, auth_key, isbn13),
    )
    return BookInfo(
        isbn13=detail.get("isbn13", isbn13),
        title=detail["title"],
        authors=detail["authors"],
        publisher=detail["publisher"],
        class_no=detail["class_no"],
        class_nm=detail["class_nm"],
        keywords=keywords,
    )


async def fetch_books_parallel(
    auth_key: str,
    isbn_list: list[str],
) -> list[BookInfo]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        detail_by_isbn: dict[str, dict] = {}
        for start in range(0, len(isbn_list), DETAIL_BATCH_SIZE):
            chunk = isbn_list[start : start + DETAIL_BATCH_SIZE]
            batch = await fetch_book_details_batch(client, auth_key, chunk)
            for d in batch:
                isbn13 = d.get("isbn13", "")
                if isbn13:
                    detail_by_isbn[isbn13] = d

        missing = [isbn for isbn in isbn_list if isbn not in detail_by_isbn]
        if not missing:
            keyword_tasks = [
                fetch_keywords(client, auth_key, isbn) for isbn in isbn_list
            ]
            keyword_results = await asyncio.gather(*keyword_tasks, return_exceptions=True)
            books = []
            for i, isbn in enumerate(isbn_list):
                if isinstance(keyword_results[i], Exception):
                    print(f"[WARN] ISBN {isbn} 키워드 조회 실패: {keyword_results[i]}")
                    continue
                detail = detail_by_isbn[isbn]
                books.append(BookInfo(
                    isbn13=isbn,
                    title=detail["title"],
                    authors=detail["authors"],
                    publisher=detail["publisher"],
                    class_no=detail["class_no"],
                    class_nm=detail["class_nm"],
                    keywords=keyword_results[i],
                ))
            return books

        all_books: list[BookInfo] = []
        have_detail = [isbn for isbn in isbn_list if isbn in detail_by_isbn]
        if have_detail:
            kw_tasks = [fetch_keywords(client, auth_key, isbn) for isbn in have_detail]
            kw_results = await asyncio.gather(*kw_tasks, return_exceptions=True)
            for i, isbn in enumerate(have_detail):
                if isinstance(kw_results[i], Exception):
                    print(f"[WARN] ISBN {isbn} 키워드 조회 실패: {kw_results[i]}")
                    continue
                d = detail_by_isbn[isbn]
                all_books.append(BookInfo(
                    isbn13=isbn,
                    title=d["title"],
                    authors=d["authors"],
                    publisher=d["publisher"],
                    class_no=d["class_no"],
                    class_nm=d["class_nm"],
                    keywords=kw_results[i],
                ))
        single_tasks = [_fetch_single_book(client, auth_key, isbn) for isbn in missing]
        single_results = await asyncio.gather(*single_tasks, return_exceptions=True)
        for i, res in enumerate(single_results):
            if isinstance(res, Exception):
                print(f"[WARN] ISBN {missing[i]} 조회 실패: {res}")
                continue
            all_books.append(res)

        order = {isbn: idx for idx, isbn in enumerate(isbn_list)}
        all_books.sort(key=lambda b: order.get(b.isbn13, 999999))
        return all_books


def _get_api_error_message(data: dict) -> str | None:
    """API가 200으로 반환했지만 본문에 에러가 있는 경우 메시지 추출."""
    res = data.get("response", {}) or {}
    if isinstance(res, dict) and res.get("error"):
        return str(res["error"])
    result = res.get("result") if isinstance(res.get("result"), dict) else {}
    msg = (result or {}).get("message") or res.get("message")
    if msg:
        return str(msg)
    return None


async def _fetch_popular_by_kdc(
    client: httpx.AsyncClient,
    auth_key: str,
    kdc: str,
    page_size: int = 200,
) -> list[str]:
    resp = await client.get(
        f"{BASE_URL}/loanItemSrch",
        params={
            "authKey": auth_key,
            "kdc": kdc,
            "pageSize": str(page_size),
            "format": "json",
        },
    )
    resp.raise_for_status()
    data = resp.json()

    err = _get_api_error_message(data)
    if err:
        raise RuntimeError(f"API 오류: {err}")

    isbns: list[str] = []
    docs = data.get("response", {}).get("docs", [])
    if isinstance(docs, dict):
        docs = [docs]
    for doc in docs:
        entry = doc.get("doc", doc)
        isbn = entry.get("isbn13") or entry.get("isbn") or ""
        if isbn:
            isbns.append(str(isbn).strip())
    return isbns


async def fetch_random_books(
    auth_key: str,
    count: int = 10,
) -> list[BookInfo]:
    selected_kdcs = random.sample(KDC_CATEGORIES, k=min(count, len(KDC_CATEGORIES)))

    async with httpx.AsyncClient(timeout=30.0) as client:
        kdc_tasks = [
            _fetch_popular_by_kdc(client, auth_key, kdc, page_size=200)
            for kdc, _ in selected_kdcs
        ]
        kdc_results = await asyncio.gather(*kdc_tasks, return_exceptions=True)

    isbn_pool: list[tuple[str, str]] = []
    for i, result in enumerate(kdc_results):
        if isinstance(result, Exception):
            print(f"[WARN] KDC {selected_kdcs[i][1]} 조회 실패: {result}")
            continue
        kdc_name = selected_kdcs[i][1]
        for isbn in result:
            isbn_pool.append((isbn, kdc_name))

    if not isbn_pool:
        if not auth_key or auth_key == os.getenv("OPENAI_API_KEY", ""):
            print("[안내] 정보나루 API 키가 없거나 OPENAI_API_KEY와 동일합니다. .env에 LIBRARY_API_KEY를 설정하세요.")
            print("       발급: https://www.data4library.kr/")
        return []

    random.shuffle(isbn_pool)

    picked_isbns: list[str] = []
    seen: set[str] = set()
    for isbn, _ in isbn_pool:
        if isbn not in seen:
            seen.add(isbn)
            picked_isbns.append(isbn)
        if len(picked_isbns) >= count * 2:
            break

    print(f"  후보 ISBN {len(picked_isbns)}개 중 키워드 있는 10권 선별 중...")

    books = await fetch_books_parallel(auth_key, picked_isbns)

    result: list[BookInfo] = []
    for b in books:
        if b.keywords and b.title:
            result.append(b)
        if len(result) >= count:
            break
    return result
