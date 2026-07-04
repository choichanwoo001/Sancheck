## BookJuk Books API 명세

**버전:** 1.0  
**최종 정리일:** 2026-03-27

이 문서는 BookJukBookJuk에서 사용하는 **Books/검색/서점 조회 API**를 정리한 것이다.  
인증/유저 프로필 등은 별도 문서를 따르고, 여기서는 홈 피드, 섹션 전체보기, 통합 검색, 책 상세, 근처 서점 조회만 다룬다.

---

### 공통 규칙

> 공통 요청 형식, 공통 에러 코드는 `API_Common.md` 참고.

- **Base URL (Books):** `/api/books`
- **Base URL (Search):** `/api`
- **인증:** 선택(옵셔널). 세션 쿠키 또는 `Authorization: Bearer <app-session-token>`  
  - 미인증: 공개 데이터만 반환
  - 인증: 개인화 섹션/내 상태 필드 추가 반환
- **에러 응답 포맷(공통):**

```json
{
  "error": "ERROR_CODE",
  "message": "사람이 읽을 수 있는 에러 설명"
}
```

---

## 1. 홈 피드 조회

### 1.1 GET `/api/books/feed`

- **설명:** 홈 화면에서 필요한 섹션 데이터를 한 번에 조회
- **인증:** 선택
  - 비로그인: `personalized`는 빈 배열
  - 로그인: `personalized`에 벡터 유사도 기반 추천 포함
- **섹션 구성:**
  - `shelf_continue`: 최근 읽는중 + 찜한 책 (최대 10)
  - `hot_ranking`: 최근 N일 별점 수 기반 HOT 랭킹 (최대 10)
  - `high_rated`: 평균 별점 상위 (최대 10)
  - `personalized`: 취향 저격 추천 (로그인 유저만, 최대 10)

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/books/feed" \
  -H "Authorization: Bearer <app-session-token>"
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | N |
| Authorization | `Bearer <app-session-token>` | N |

#### 3. Request Element

- Path/Query/Body 없음.

#### 4. Response

**200 OK**

```json
{
  "shelf_continue": [
    {
      "book_id": 101,
      "title": "데미안",
      "cover_image_url": "https://cdn.example.com/books/101.jpg",
      "avg_rating": 4.2
    }
  ],
  "hot_ranking": [
    {
      "book_id": 203,
      "title": "소년이 온다",
      "cover_image_url": "https://cdn.example.com/books/203.jpg",
      "avg_rating": 4.6
    }
  ],
  "high_rated": [
    {
      "book_id": 305,
      "title": "작별하지 않는다",
      "cover_image_url": "https://cdn.example.com/books/305.jpg",
      "avg_rating": 4.8
    }
  ],
  "personalized": [
    {
      "book_id": 409,
      "title": "아침 그리고 저녁",
      "cover_image_url": "https://cdn.example.com/books/409.jpg",
      "avg_rating": 4.1
    }
  ]
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 500 | INTERNAL_SERVER_ERROR | 피드 집계 중 서버 내부 오류 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 2. 홈 섹션 전체보기

### 2.1 GET `/api/books/feed/{section_type}`

- **설명:** 특정 섹션의 전체 목록을 페이지네이션으로 조회 (3열 그리드용)
- **인증:** 선택
  - `personalized`는 로그인 유저 기준으로만 채워짐 (비로그인 시 빈 목록)

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/books/feed/hot_ranking?page=1&per_page=30" \
  -H "Authorization: Bearer <app-session-token>"
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | N |
| Authorization | `Bearer <app-session-token>` | N |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| section_type | string | Y | Path. `shelf_continue` \| `hot_ranking` \| `high_rated` \| `personalized` |
| page | integer | N | 페이지 번호(1-base), default=1 |
| per_page | integer | N | 페이지당 항목 수, default=30 |

#### 4. Response

**200 OK**

```json
{
  "section_type": "hot_ranking",
  "items": [
    {
      "book_id": 203,
      "title": "소년이 온다",
      "cover_image_url": "https://cdn.example.com/books/203.jpg",
      "avg_rating": 4.6
    }
  ],
  "page": 1,
  "per_page": 30,
  "total_count": 126
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | INVALID_SECTION_TYPE | 지원하지 않는 section_type |
| 500 | INTERNAL_SERVER_ERROR | 섹션 조회 중 서버 내부 오류 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 3. 통합 검색

### 3.1 GET `/api/search`

- **설명:** 책/저자/컬렉션/유저 통합 검색
- **비고:** Books API가 아닌 `/api` Base URL 사용

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/search?q=데미안&type=books"
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | N |
| Authorization | `Bearer <app-session-token>` | N |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| q | string | Y | 검색어 |
| type | string | N | `books` \| `authors` \| `collections` \| `users`, 생략 시 전체 |

#### 4. Response

**200 OK**

```json
{
  "books": [
    {
      "book_id": 101,
      "title": "데미안",
      "cover_image_url": "https://cdn.example.com/books/101.jpg",
      "avg_rating": 4.2
    }
  ],
  "authors": [
    {
      "author_id": 1,
      "name": "헤르만 헤세"
    }
  ],
  "collections": [
    {
      "collection_id": 10,
      "title": "퇴근 후 읽는 고전",
      "user_nickname": "ara"
    }
  ],
  "users": [
    {
      "user_id": 77,
      "nickname": "ara",
      "profile_image_url": "https://cdn.example.com/profiles/77.png"
    }
  ]
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | MISSING_QUERY | `q` 누락 |
| 400 | INVALID_TYPE | 지원하지 않는 type |
| 500 | INTERNAL_SERVER_ERROR | 통합 검색 처리 중 서버 내부 오류 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 4. 책 상세 조회

### 4.1 GET `/api/books/{book_id}`

- **설명:** 도서 상세 정보 조회
- **인증:** 선택
  - 로그인: `my_rating`, `my_shelf_state` 포함
  - 비로그인: `my_rating=null`, `my_shelf_state=null`
- **비고:** `description`, `author_bio`는 `book_api_cache`(isbn 기준)에서 우선 조회하고, 만료(`expires_at`) 시 백엔드에서 외부 API 재호출 후 갱신

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/books/101" \
  -H "Authorization: Bearer <app-session-token>"
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | N |
| Authorization | `Bearer <app-session-token>` | N |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| book_id | integer \| string | Y | Path. 도서 ID |

#### 4. Response

**200 OK**

```json
{
  "book_id": 1,
  "isbn": "9788937460470",
  "title": "예시 제목",
  "cover_image_url": "https://cdn.example.com/books/1.jpg",
  "publication_year": 2021,
  "category": "소설",
  "avg_rating": 3.5,
  "rating_count": 128,
  "authors": [
    {
      "author_id": 1,
      "name": "홍길동",
      "role": "저자"
    }
  ],
  "description": "책 소개",
  "author_bio": "저자 소개",
  "my_rating": 4.0,
  "my_shelf_state": "READING"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 404 | NOT_FOUND | 도서 없음 |
| 500 | INTERNAL_SERVER_ERROR | 상세 조회 중 서버 내부 오류 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 5. 근처 서점 조회

### 5.1 GET `/api/books/{book_id}/nearby-stores`

- **설명:** 특정 책 기준으로 사용자 현재 위치 주변 서점 목록 조회
- **비고:** 거리 계산은 `stores.latitude`, `stores.longitude` 기반

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/books/101/nearby-stores?latitude=37.5665&longitude=126.9780&radius_km=5"
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | N |
| Authorization | `Bearer <app-session-token>` | N |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| book_id | integer \| string | Y | Path. 도서 ID |
| latitude | number | Y | 사용자 현재 위도 |
| longitude | number | Y | 사용자 현재 경도 |
| radius_km | number | N | 조회 반경(km), default=5 |

#### 4. Response

**200 OK**

```json
[
  {
    "store_id": 11,
    "name": "북라운지 합정점",
    "address": "서울 마포구 ...",
    "latitude": 37.5523,
    "longitude": 126.9124,
    "distance_km": 1.28
  }
]
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | MISSING_LOCATION | latitude 또는 longitude 누락 |
| 404 | NOT_FOUND | 도서 없음 |
| 500 | INTERNAL_SERVER_ERROR | 근처 서점 조회 중 서버 내부 오류 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 6. 데이터 소스/내부 로직 메모

- `books`: 도서 기본 메타데이터 소스
- `authors`, `book_authors`: 도서-저자 관계 구성
- `ratings`: `avg_rating`, `rating_count` 집계 소스
- `book_api_cache`: 외부 API 캐시(클라이언트 비노출), `expires_at` 만료 시 재조회
- `book_vectors`: 개인화 추천(`personalized`)용 벡터/메타 데이터
- `stores`: 위치 기반 근처 서점 계산 소스

