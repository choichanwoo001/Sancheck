"""3개 데이터 소스 (정보나루, 알라딘, Wikipedia) 에서 책 관련 데이터를 수집해
BookContext dataclass 로 반환한다.
"""
from __future__ import annotations

import asyncio
import re
import sys
import os
from dataclasses import dataclass, field

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from library_api import fetch_book_detail, fetch_keywords, BookKeyword

ALADIN_BASE = "https://www.aladin.co.kr/ttb/api"
_WIKI_403_WARNED = False
WIKI_MAX_SECTIONS = 6
WIKI_SECTION_DELAY_SEC = 0.25


def _wiki_headers() -> dict[str, str]:
    """
    Wikimedia는 User-Agent에 프로젝트 식별 + 연락처(이메일 등)를 권장/요구하는 경우가 있다.
    예) BookChatBot/1.0 (mailto:me@example.com)
    """
    ua = os.getenv("WIKI_USER_AGENT", "").strip()
    if not ua:
        ua = "BookChatBot/1.0 (mailto:your_email@example.com)"
    return {"User-Agent": ua, "Accept": "application/json"}


@dataclass
class BookContext:
    isbn13: str
    title: str
    authors: str
    publisher: str
    published_year: str
    description: str
    author_bio: str
    editorial_review: str
    keywords: list[BookKeyword]
    subject_names: list[str]
    kdc_class: str
    wiki_book_summary: str
    wiki_author_summary: str
    wiki_extra_sections: list[dict]
    raw_docs: list[dict] = field(default_factory=list)


async def _fetch_aladin(
    client: httpx.AsyncClient,
    api_key: str,
    isbn13: str,
) -> dict:
    if not api_key:
        return {}
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
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("item", [])
        return items[0] if items else {}
    except Exception as e:
        print(f"[WARN] 알라딘 API 실패 (ISBN {isbn13}): {e}")
        return {}


async def _fetch_aladin_by_title(
    client: httpx.AsyncClient,
    api_key: str,
    title: str,
    author: str = "",
) -> dict:
    if not api_key:
        return {}
    try:
        query = f"{title} {author}".strip()
        resp = await client.get(
            f"{ALADIN_BASE}/ItemSearch.aspx",
            params={
                "ttbkey": api_key,
                "Query": query,
                "QueryType": "Keyword",
                "MaxResults": "1",
                "output": "js",
                "Version": "20131101",
                "OptResult": "authorInfo,Toc,story,reviewList",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("item", [])
        return items[0] if items else {}
    except Exception as e:
        print(f"[WARN] 알라딘 검색 실패 ('{title}'): {e}")
        return {}


async def _fetch_wikipedia_summary(
    client: httpx.AsyncClient,
    title: str,
    lang: str = "ko",
) -> str:
    # NOTE: Wikimedia REST v1 은 환경에 따라 403 이 발생할 수 있어
    # MediaWiki Action API(w/api.php)로 우회한다.
    page_title = title.strip()
    if not page_title:
        return ""
    try:
        resp = await client.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "extracts",
                "exintro": "1",
                "explaintext": "1",
                "redirects": "1",
                "titles": page_title,
            },
            timeout=15.0,
            headers=_wiki_headers(),
        )
        if resp.status_code == 403:
            global _WIKI_403_WARNED
            if not _WIKI_403_WARNED:
                _WIKI_403_WARNED = True
                print(
                    "[WARN] Wikipedia 요청이 403으로 차단되었습니다.\n"
                    "       - 우선 .env에 WIKI_USER_AGENT를 '앱명/버전 (mailto:이메일)' 형식으로 설정해보세요.\n"
                    "       - 그래도 안되면 IP/네트워크에서 차단된 상태일 수 있어 Wikipedia 데이터는 비활성화됩니다."
                )
            return ""
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return ""
        page = pages[0]
        if page.get("missing"):
            return ""
        extract = page.get("extract") or ""
        return str(extract).strip()
    except httpx.HTTPStatusError as e:
        # 일부 환경에서 Wikimedia가 차단되는 경우가 있어, 기능은 계속 진행한다.
        if getattr(e.response, "status_code", None) == 403:
            return ""
        print(f"[WARN] Wikipedia '{title}' ({lang}) 실패: {e}")
        return ""
    except Exception as e:
        print(f"[WARN] Wikipedia '{title}' ({lang}) 실패: {e}")
        return ""


async def _fetch_wikipedia_sections(
    client: httpx.AsyncClient,
    title: str,
    lang: str = "ko",
) -> list[dict]:
    page_title = title.strip()
    if not page_title:
        return []
    try:
        # 1) 섹션 목록 조회
        resp = await client.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "parse",
                "format": "json",
                "page": page_title,
                "prop": "sections",
                "redirects": "1",
            },
            timeout=15.0,
            headers=_wiki_headers(),
        )
        if resp.status_code == 403:
            return []
        resp.raise_for_status()
        data = resp.json()
        raw_sections = data.get("parse", {}).get("sections", []) or []

        # 2) 상위 몇 개 섹션만 본문을 가져온다 (너무 많은 API 호출 방지)
        sections: list[dict] = []
        for sec in raw_sections[:WIKI_MAX_SECTIONS]:
            index = sec.get("index")
            line = sec.get("line", "")
            if not index or not line:
                continue

            # 섹션 본문 조회 (HTML -> 텍스트)
            await asyncio.sleep(WIKI_SECTION_DELAY_SEC)
            sec_resp = await client.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "parse",
                    "format": "json",
                    "page": page_title,
                    "prop": "text",
                    "section": str(index),
                    "redirects": "1",
                },
                timeout=15.0,
                headers=_wiki_headers(),
            )
            if sec_resp.status_code == 403:
                return []
            sec_resp.raise_for_status()
            sec_data = sec_resp.json()
            html = (
                sec_data.get("parse", {})
                .get("text", {})
                .get("*", "")
            )
            clean_text = re.sub(r"<[^>]+>", "", html).strip()
            clean_text = re.sub(r"\\s+", " ", clean_text).strip()
            if clean_text and len(clean_text) > 80:
                sections.append({"title": line, "text": clean_text[:2000]})

        return sections
    except httpx.HTTPStatusError as e:
        if getattr(e.response, "status_code", None) == 403:
            return []
        print(f"[WARN] Wikipedia 섹션 '{title}' ({lang}) 실패: {e}")
        return []
    except Exception as e:
        print(f"[WARN] Wikipedia 섹션 '{title}' ({lang}) 실패: {e}")
        return []


async def collect_book_context(
    isbn13: str | None = None,
    title: str | None = None,
    author: str | None = None,
    library_api_key: str = "",
    aladin_api_key: str = "",
) -> BookContext:
    """3개 API 에서 책 컨텍스트를 수집한다.
    isbn13 이 없으면 title + author 로 알라딘에서 먼저 검색한다.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        # ── 알라딘 조회 ────────────────────────────────────────
        if isbn13 and aladin_api_key:
            aladin_item = await _fetch_aladin(client, aladin_api_key, isbn13)
        elif title and aladin_api_key:
            aladin_item = await _fetch_aladin_by_title(client, aladin_api_key, title, author or "")
            if aladin_item and not isbn13:
                isbn13 = aladin_item.get("isbn13", "") or aladin_item.get("isbn", "")
        else:
            aladin_item = {}

        resolved_isbn = isbn13 or ""
        resolved_title = title or aladin_item.get("title", "")
        resolved_author = author or aladin_item.get("author", "")
        description = aladin_item.get("description", "")

        author_bio_list = aladin_item.get("authorInfo", [])
        if isinstance(author_bio_list, list):
            author_bio = " ".join(
                a.get("authorInfo", "") for a in author_bio_list if isinstance(a, dict)
            )
        else:
            author_bio = aladin_item.get("authorInfoAdd", "")

        editorial_reviews = aladin_item.get("reviewList", []) or []
        editorial_review = " ".join(
            r.get("reviewRank", "") + " " + r.get("reviewText", "")
            for r in editorial_reviews
            if isinstance(r, dict)
        )
        publisher = aladin_item.get("publisher", "")
        pub_date = aladin_item.get("pubDate", "")

        # ── 정보나루 조회 (isbn13 있을 때만) ──────────────────
        library_keywords: list[BookKeyword] = []
        kdc_class = ""
        library_title = resolved_title
        library_author = resolved_author

        if resolved_isbn and library_api_key:
            try:
                library_keywords, library_detail = await asyncio.gather(
                    fetch_keywords(client, library_api_key, resolved_isbn),
                    fetch_book_detail(client, library_api_key, resolved_isbn),
                )
                if library_detail.get("title"):
                    library_title = library_detail["title"]
                if library_detail.get("authors"):
                    library_author = library_detail["authors"]
                kdc_class = library_detail.get("class_nm", "")
            except Exception as e:
                print(f"[WARN] 정보나루 조회 실패: {e}")

        final_title = (library_title or resolved_title).strip()
        final_author = (library_author or resolved_author).strip()

        # ── Wikipedia 조회 (책 + 작가) ────────────────────────
        wiki_book = await _fetch_wikipedia_summary(client, final_title, "ko")
        if not wiki_book and final_title:
            wiki_book = await _fetch_wikipedia_summary(client, final_title, "en")

        wiki_author = ""
        if final_author:
            # "지은이: 헤르만 헤세", "저자: 홍길동" 같은 역할 접두어 제거 후 첫 번째 이름 추출
            raw_name = re.split(r"[,;|（(]", final_author)[0].strip()
            author_name = re.sub(r"^[^:：]+[:：]\s*", "", raw_name).strip()
            wiki_author = await _fetch_wikipedia_summary(client, author_name, "ko")
            if not wiki_author:
                wiki_author = await _fetch_wikipedia_summary(client, author_name, "en")

        wiki_sections = await _fetch_wikipedia_sections(client, final_title, "ko")
        if not wiki_sections and final_title:
            wiki_sections = await _fetch_wikipedia_sections(client, final_title, "en")

    # ── 원문 문서 목록 조립 (벡터 스토어용) ───────────────────
    # 정책:
    # - 그래프 전용: keywords, wiki section (관계/엔티티 추출용)
    # - 중복 허용(그래프 + 벡터): 책 핵심 요약, 작가 핵심 소개
    #   * 책 핵심 요약: 알라딘 description (없으면 wiki_book)
    #   * 작가 핵심 소개: wiki_author (없으면 aladin author_bio)
    # - 벡터 전용: editorial_review (서술형 감상 맥락)
    raw_docs: list[dict] = []

    # (중복 1) 책 핵심 요약
    if description:
        raw_docs.append({"text": description, "source": "알라딘", "doc_type": "description"})
    elif wiki_book:
        raw_docs.append({"text": wiki_book, "source": "위키피디아", "doc_type": "summary"})

    # (중복 2) 작가 핵심 소개
    if wiki_author:
        raw_docs.append({"text": wiki_author, "source": "위키피디아", "doc_type": "biography"})
    elif author_bio:
        raw_docs.append({"text": author_bio, "source": "알라딘", "doc_type": "biography"})

    # 벡터 전용(긴 서술 텍스트)
    if editorial_review:
        raw_docs.append({"text": editorial_review, "source": "알라딘", "doc_type": "review"})

    return BookContext(
        isbn13=resolved_isbn,
        title=final_title,
        authors=final_author,
        publisher=publisher,
        published_year=pub_date[:4] if pub_date else "",
        description=description,
        author_bio=author_bio,
        editorial_review=editorial_review,
        keywords=library_keywords,
        subject_names=[],
        kdc_class=kdc_class,
        wiki_book_summary=wiki_book,
        wiki_author_summary=wiki_author,
        wiki_extra_sections=wiki_sections,
        raw_docs=raw_docs,
    )
