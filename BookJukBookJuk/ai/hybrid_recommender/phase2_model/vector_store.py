"""책 단위 벡터 DB: numpy 인메모리 + 선택적 Pinecone 연동

기존 book_chat/vector_store.py 는 단일 책의 청크 단위 벡터를 다루지만,
여기서는 책 1권 = 벡터 1개 형태의 book-level 벡터 저장소를 구현한다.

Optional Pinecone 연동으로 대규모 카탈로그를 지원한다.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

EMBEDDING_DIM = 1536


@dataclass
class BookVector:
    """책 한 권의 벡터 표현."""
    isbn13: str
    title: str
    authors: str
    vector: np.ndarray
    kdc_class: str = ""
    publisher: str = ""
    published_year: str = ""
    is_cold_start: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "isbn13": self.isbn13,
            "title": self.title,
            "authors": self.authors,
            "kdc_class": self.kdc_class,
            "publisher": self.publisher,
            "published_year": self.published_year,
            "is_cold_start": self.is_cold_start,
            **self.metadata,
        }


@dataclass
class SearchResult:
    book: BookVector
    score: float  # 코사인 유사도 (0~1)


# ── numpy 인메모리 벡터 스토어 ────────────────────────────────────────────────


class BookVectorStore:
    """책 단위 벡터 저장소.

    numpy 배열로 코사인 유사도 검색을 수행한다.
    Pinecone 이 설치된 환경에서는 선택적으로 Pinecone 으로 위임한다.
    """

    def __init__(self, use_pinecone: bool = False, pinecone_config: dict | None = None) -> None:
        self._books: list[BookVector] = []
        self._matrix: np.ndarray | None = None  # [n_books, dim] 캐시
        self._matrix_dirty: bool = True

        self._pinecone = None
        if use_pinecone and pinecone_config:
            self._init_pinecone(pinecone_config)

    def _init_pinecone(self, config: dict) -> None:
        """Pinecone 연결 초기화 (선택적)."""
        try:
            from pinecone import Pinecone, ServerlessSpec  # type: ignore[import]
            pc = Pinecone(api_key=config["api_key"])
            index_name = config.get("index_name", "bookjuk-books")
            if index_name not in pc.list_indexes().names():
                pc.create_index(
                    name=index_name,
                    dimension=EMBEDDING_DIM,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud=config.get("cloud", "aws"),
                        region=config.get("region", "us-east-1"),
                    ),
                )
            self._pinecone = pc.Index(index_name)
            print(f"[INFO] Pinecone 연결 성공: index={index_name}")
        except ImportError:
            print("[WARN] pinecone 패키지 미설치. numpy 모드로 동작합니다.")
        except Exception as e:
            print(f"[WARN] Pinecone 초기화 실패: {e}. numpy 모드로 동작합니다.")

    def add(self, book_vector: BookVector) -> None:
        """책 벡터를 추가한다. 동일 isbn13 이면 업데이트."""
        for i, bv in enumerate(self._books):
            if bv.isbn13 == book_vector.isbn13:
                self._books[i] = book_vector
                self._matrix_dirty = True
                self._upsert_pinecone(book_vector)
                return

        self._books.append(book_vector)
        self._matrix_dirty = True
        self._upsert_pinecone(book_vector)

    def _upsert_pinecone(self, bv: BookVector) -> None:
        if self._pinecone is None:
            return
        try:
            self._pinecone.upsert(vectors=[{
                "id": bv.isbn13,
                "values": bv.vector.tolist(),
                "metadata": bv.to_dict(),
            }])
        except Exception as e:
            print(f"[WARN] Pinecone upsert 실패 ({bv.isbn13}): {e}")

    def _rebuild_matrix(self) -> None:
        if not self._books:
            self._matrix = None
            return
        self._matrix = np.stack([bv.vector for bv in self._books])
        self._matrix_dirty = False

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        exclude_isbns: list[str] | None = None,
    ) -> list[SearchResult]:
        """코사인 유사도로 가장 유사한 책을 검색한다.

        Args:
            query_vector: 1536차원 쿼리 벡터
            top_k: 반환할 최대 결과 수
            exclude_isbns: 검색 결과에서 제외할 ISBN 목록 (사용자 이미 읽은 책 등)
        """
        if self._pinecone is not None:
            return self._search_pinecone(query_vector, top_k, exclude_isbns)
        return self._search_numpy(query_vector, top_k, exclude_isbns)

    def _search_numpy(
        self,
        query_vector: np.ndarray,
        top_k: int,
        exclude_isbns: list[str] | None,
    ) -> list[SearchResult]:
        if self._matrix_dirty:
            self._rebuild_matrix()
        if self._matrix is None or len(self._books) == 0:
            return []

        exclude_set = set(exclude_isbns or [])

        # 코사인 유사도 계산 (이미 정규화된 벡터 가정)
        q = query_vector / (np.linalg.norm(query_vector) + 1e-9)
        scores = self._matrix @ q  # [n_books]

        # 내림차순 정렬
        sorted_indices = np.argsort(scores)[::-1]

        results: list[SearchResult] = []
        for idx in sorted_indices:
            bv = self._books[idx]
            if bv.isbn13 in exclude_set:
                continue
            results.append(SearchResult(book=bv, score=float(scores[idx])))
            if len(results) >= top_k:
                break

        return results

    def _search_pinecone(
        self,
        query_vector: np.ndarray,
        top_k: int,
        exclude_isbns: list[str] | None,
    ) -> list[SearchResult]:
        try:
            response = self._pinecone.query(
                vector=query_vector.tolist(),
                top_k=top_k + len(exclude_isbns or []) + 5,
                include_metadata=True,
            )
            exclude_set = set(exclude_isbns or [])
            results: list[SearchResult] = []
            for match in response.matches:
                if match.id in exclude_set:
                    continue
                meta = match.metadata or {}
                # Pinecone 결과를 BookVector 로 재구성 (벡터 없이 메타만)
                bv = BookVector(
                    isbn13=match.id,
                    title=meta.get("title", ""),
                    authors=meta.get("authors", ""),
                    vector=np.zeros(EMBEDDING_DIM),
                    kdc_class=meta.get("kdc_class", ""),
                    publisher=meta.get("publisher", ""),
                    published_year=meta.get("published_year", ""),
                )
                results.append(SearchResult(book=bv, score=float(match.score)))
                if len(results) >= top_k:
                    break
            return results
        except Exception as e:
            print(f"[WARN] Pinecone 검색 실패: {e}. numpy 모드로 전환합니다.")
            return self._search_numpy(query_vector, top_k, exclude_isbns)

    def get_vector(self, isbn13: str) -> np.ndarray | None:
        """ISBN 으로 책 벡터를 조회한다."""
        for bv in self._books:
            if bv.isbn13 == isbn13:
                return bv.vector
        return None

    def get_book(self, isbn13: str) -> BookVector | None:
        """ISBN 으로 BookVector 를 조회한다."""
        for bv in self._books:
            if bv.isbn13 == isbn13:
                return bv
        return None

    def get_all_isbns(self) -> list[str]:
        return [bv.isbn13 for bv in self._books]

    def __len__(self) -> int:
        return len(self._books)

    def save(self, path: str | Path) -> None:
        """저장소를 파일로 직렬화한다."""
        with open(path, "wb") as f:
            pickle.dump(self._books, f)

    @classmethod
    def load(cls, path: str | Path) -> "BookVectorStore":
        """파일에서 저장소를 복원한다."""
        store = cls()
        with open(path, "rb") as f:
            store._books = pickle.load(f)
        store._matrix_dirty = True
        return store
