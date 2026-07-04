## BookJuk Shelf & Ratings API 명세

**버전:** 1.0  
**최종 정리일:** 2026-03-27

이 문서는 BookJukBookJuk에서 사용하는 **보관함/별점 API**를 정리한 것이다.  
인증/유저 프로필 등은 별도 문서를 따르고, 여기서는 보관함 조회/추가/삭제, 별점 등록/삭제, 쇼핑리스트 조회만 다룬다.

---

### 공통 규칙

> 공통 요청 형식, 공통 에러 코드는 `API_Common.md` 참고.

- **Base URL:** `/api`
- **인증:** 필수. 세션 쿠키 또는 `Authorization: Bearer <app-session-token>`
- **에러 응답 포맷(공통):**

```json
{
  "error": "ERROR_CODE",
  "message": "사람이 읽을 수 있는 에러 설명"
}
```

### 보관함 상태 규칙

- `찜한(LIST)`: 수동 추가
- `읽는중(READING)`: 수동 추가
- `쇼핑리스트`: 수동 추가 (서점 스마트카트 연동)
- `평가한`: 별점 등록 시 자동 추가 (수동 추가 불가)
- `shelf_state`는 `book_user_states`에서 관리
- `shelves`/`shelf_books`는 보관함 탭 조회용으로 사용

---

## 1. 보관함 목록 조회

### 1.1 GET `/api/shelf`

- **설명:** 인증 유저의 보관함 목록 조회

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/shelf?type=찜한" \
  -H "Authorization: Bearer <app-session-token>"
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | Cookie 또는 Authorization 중 하나 필수 |
| Authorization | `Bearer <app-session-token>` | Cookie 또는 Authorization 중 하나 필수 |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| type | string | N | `평가한` \| `찜한` \| `읽는중` \| `쇼핑리스트`, 생략 시 전체 |

#### 4. Response

**200 OK**

```json
{
  "type": "찜한",
  "books": [
    {
      "book_id": 101,
      "title": "데미안",
      "cover_image_url": "https://cdn.example.com/books/101.jpg",
      "avg_rating": 4.2,
      "added_at": "2026-03-27T10:10:00Z"
    }
  ]
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | INVALID_SHELF_TYPE | 지원하지 않는 type |
| 401 | UNAUTHORIZED | 로그인 필요 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 2. 보관함 추가/변경

### 2.1 POST `/api/shelf`

- **설명:** 보관함에 책 추가. 같은 책이 다른 탭에 있으면 이동 처리
- **중요:** `평가한`은 직접 추가 불가

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/shelf" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"book_id":101,"shelf_type":"찜한"}'
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | Cookie 또는 Authorization 중 하나 필수 |
| Authorization | `Bearer <app-session-token>` | Cookie 또는 Authorization 중 하나 필수 |
| Content-Type | `application/json` | Y |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| book_id | integer \| string | Y | 대상 도서 ID |
| shelf_type | string | Y | `찜한` \| `읽는중` \| `쇼핑리스트` |

#### 4. Response

**200 OK**

```json
{
  "book_id": 101,
  "shelf_type": "찜한",
  "moved_from": "읽는중",
  "added_at": "2026-03-27T10:20:00Z"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | INVALID_SHELF_TYPE | 지원하지 않는 shelf_type 또는 `평가한` 직접 추가 시도 |
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | NOT_FOUND | 도서 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 3. 보관함 삭제

### 3.1 DELETE `/api/shelf/{book_id}`

- **설명:** 특정 보관함 탭에서 도서 제거

#### 1. Request Syntax

```bash
curl -X DELETE "https://example.com/api/shelf/101?shelf_type=찜한" \
  -H "Authorization: Bearer <app-session-token>"
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | Cookie 또는 Authorization 중 하나 필수 |
| Authorization | `Bearer <app-session-token>` | Cookie 또는 Authorization 중 하나 필수 |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| book_id | integer \| string | Y | Path. 도서 ID |
| shelf_type | string | Y | Query. `평가한` \| `찜한` \| `읽는중` \| `쇼핑리스트` |

#### 4. Response

**200 OK**

```json
{
  "book_id": 101,
  "shelf_type": "찜한",
  "removed": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | INVALID_SHELF_TYPE | 지원하지 않는 shelf_type |
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | NOT_IN_SHELF | 해당 보관함에 도서가 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 4. 별점 등록/수정

### 4.1 PUT `/api/ratings/{book_id}`

- **설명:** 도서 별점 등록 또는 수정
- **점수 규칙:** 0.5 단위, 0.5~5.0
- **자동 처리:**
  - `book_user_states.shelf_state` -> `RATED_ONLY`
  - `평가한` 보관함 자동 추가
  - `comment_prompted=true` 반환 (프론트 모달 트리거)

#### 1. Request Syntax

```bash
curl -X PUT "https://example.com/api/ratings/101" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"score":3.5}'
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | Cookie 또는 Authorization 중 하나 필수 |
| Authorization | `Bearer <app-session-token>` | Cookie 또는 Authorization 중 하나 필수 |
| Content-Type | `application/json` | Y |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| book_id | integer \| string | Y | Path. 도서 ID |
| score | number | Y | 0.5 단위, 범위 0.5~5.0 |

#### 4. Response

**200 OK**

```json
{
  "book_id": 101,
  "score": 3.5,
  "registered_at": "2026-03-27T10:30:00Z",
  "comment_prompted": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | INVALID_SCORE | 0.5 단위 아님 또는 허용 범위 초과/미만 |
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | NOT_FOUND | 도서 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 5. 별점 삭제

### 5.1 DELETE `/api/ratings/{book_id}`

- **설명:** 별점 삭제
- **자동 처리:** `평가한` 보관함에서 자동 제거

#### 1. Request Syntax

```bash
curl -X DELETE "https://example.com/api/ratings/101" \
  -H "Authorization: Bearer <app-session-token>"
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | Cookie 또는 Authorization 중 하나 필수 |
| Authorization | `Bearer <app-session-token>` | Cookie 또는 Authorization 중 하나 필수 |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| book_id | integer \| string | Y | Path. 도서 ID |

#### 4. Response

**200 OK**

```json
{
  "book_id": 101,
  "removed": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | RATING_NOT_FOUND | 기존 별점 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 6. 쇼핑리스트 조회

### 6.1 GET `/api/shelf/shopping-list`

- **설명:** 서점 스마트카트 연동용 쇼핑리스트 조회

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/shelf/shopping-list" \
  -H "Authorization: Bearer <app-session-token>"
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | Cookie 또는 Authorization 중 하나 필수 |
| Authorization | `Bearer <app-session-token>` | Cookie 또는 Authorization 중 하나 필수 |

#### 3. Request Element

- Path/Query/Body 없음.

#### 4. Response

**200 OK**

```json
[
  {
    "book_id": 101,
    "title": "데미안",
    "isbn": "9788937460470",
    "cover_image_url": "https://cdn.example.com/books/101.jpg"
  }
]
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 7. 데이터 소스/내부 로직 메모

- `ratings`: `(user_id, book_id)` PK 기반 upsert/삭제
- `book_user_states`: `shelf_state`, `comment_prompted_at`, `context_tags` 상태 관리
- `shelves` + `shelf_books`: 보관함 탭별 목록 조회용
- 별점 등록 시 `RATED_ONLY` 전이 + `평가한` 탭 자동 반영

