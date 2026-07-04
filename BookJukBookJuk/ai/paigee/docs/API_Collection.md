## BookJuk Collection API 명세

**버전:** 1.0  
**최종 정리일:** 2026-03-27

이 문서는 BookJukBookJuk에서 사용하는 **컬렉션 API**를 정리한 것이다.  
인증/유저 프로필 등은 별도 문서를 따르고, 여기서는 컬렉션 조회/생성/수정/삭제와 컬렉션 내 도서 관리만 다룬다.

---

### 공통 규칙

> 공통 요청 형식, 공통 에러 코드는 `API_Common.md` 참고.

- **Base URL:** `/api`
- **인증:** 엔드포인트별 상이 (선택 또는 필수)
- **에러 응답 포맷(공통):**

```json
{
  "error": "ERROR_CODE",
  "message": "사람이 읽을 수 있는 에러 설명"
}
```

---

## 1. 내 컬렉션 목록 조회

### 1.1 GET `/api/collections`

- **설명:** 현재 로그인 유저의 컬렉션 목록 조회

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/collections" \
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
    "collection_id": 1,
    "title": "퇴근 후 읽는 책",
    "description": "짧게 몰입할 수 있는 책들",
    "is_public": true,
    "book_count": 12,
    "cover_images": [
      "https://cdn.example.com/books/101.jpg",
      "https://cdn.example.com/books/203.jpg",
      "https://cdn.example.com/books/305.jpg"
    ],
    "created_at": "2026-03-27T09:00:00Z"
  }
]
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 2. 특정 유저의 컬렉션 목록 조회

### 2.1 GET `/api/users/{user_id}/collections`

- **설명:** 프로필 페이지용 특정 유저의 컬렉션 목록 조회
- **인증:** 선택
  - 비로그인 또는 타인: `is_public=true`만 반환
  - 본인: 전체 반환

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/users/77/collections" \
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
| user_id | integer \| string | Y | Path. 대상 유저 ID |

#### 4. Response

**200 OK**

```json
[
  {
    "collection_id": 3,
    "title": "봄에 읽기 좋은 소설",
    "description": "가볍게 시작하는 목록",
    "is_public": true,
    "book_count": 7,
    "cover_images": [
      "https://cdn.example.com/books/501.jpg",
      "https://cdn.example.com/books/502.jpg"
    ],
    "created_at": "2026-03-20T08:30:00Z"
  }
]
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 404 | NOT_FOUND | 유저 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 3. 컬렉션 상세 조회

### 3.1 GET `/api/collections/{collection_id}`

- **설명:** 컬렉션 메타데이터와 도서 목록 상세 조회
- **인증:** 선택
- **권한 규칙:** 비공개 컬렉션은 본인만 조회 가능

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/collections/1" \
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
| collection_id | integer \| string | Y | Path. 컬렉션 ID |

#### 4. Response

**200 OK**

```json
{
  "collection_id": 1,
  "user": {
    "user_id": 1,
    "nickname": "ara"
  },
  "title": "퇴근 후 읽는 책",
  "description": "짧게 몰입할 수 있는 책들",
  "is_public": true,
  "books": [
    {
      "order_index": 0,
      "book_id": 101,
      "title": "데미안",
      "cover_image_url": "https://cdn.example.com/books/101.jpg",
      "avg_rating": 4.0
    }
  ],
  "created_at": "2026-03-27T09:00:00Z"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 403 | FORBIDDEN | 비공개 컬렉션 타인 접근 |
| 404 | NOT_FOUND | 컬렉션 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 4. 컬렉션 생성

### 4.1 POST `/api/collections`

- **설명:** 새 컬렉션 생성

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/collections" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"title":"퇴근 후 읽는 책","description":"짧게 몰입할 수 있는 책들","is_public":true}'
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
| title | string | Y | 컬렉션 제목 |
| description | string | N | 컬렉션 설명 |
| is_public | boolean | N | 공개 여부, default=true |

#### 4. Response

**201 Created**

```json
{
  "collection_id": 44,
  "title": "퇴근 후 읽는 책",
  "is_public": true,
  "created_at": "2026-03-27T12:00:00Z"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | MISSING_TITLE | title 누락 또는 빈 문자열 |
| 401 | UNAUTHORIZED | 로그인 필요 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 5. 컬렉션 수정

### 5.1 PUT `/api/collections/{collection_id}`

- **설명:** 내 컬렉션 메타데이터 수정 (부분 수정 가능)

#### 1. Request Syntax

```bash
curl -X PUT "https://example.com/api/collections/44" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"title":"주말에 읽는 책","is_public":false}'
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
| collection_id | integer \| string | Y | Path. 컬렉션 ID |
| title | string | N | 수정할 컬렉션 제목 |
| description | string | N | 수정할 컬렉션 설명 |
| is_public | boolean | N | 공개 여부 |

#### 4. Response

**200 OK**

```json
{
  "collection_id": 44,
  "updated": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 컬렉션 아님 |
| 404 | NOT_FOUND | 컬렉션 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 6. 컬렉션 삭제

### 6.1 DELETE `/api/collections/{collection_id}`

- **설명:** 내 컬렉션 삭제 (연결된 `collection_books`도 함께 제거)

#### 1. Request Syntax

```bash
curl -X DELETE "https://example.com/api/collections/44" \
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
| collection_id | integer \| string | Y | Path. 컬렉션 ID |

#### 4. Response

**200 OK**

```json
{
  "collection_id": 44,
  "removed": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 컬렉션 아님 |
| 404 | NOT_FOUND | 컬렉션 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 7. 컬렉션에 책 추가

### 7.1 POST `/api/collections/{collection_id}/books`

- **설명:** 컬렉션에 도서 추가
- **규칙:** `order_index`는 현재 마지막 순서 + 1 자동 부여

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/collections/1/books" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"book_id":101}'
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
| collection_id | integer \| string | Y | Path. 컬렉션 ID |
| book_id | integer \| string | Y | 추가할 도서 ID |

#### 4. Response

**201 Created**

```json
{
  "collection_id": 1,
  "book_id": 101,
  "order_index": 12,
  "added_at": "2026-03-27T12:20:00Z"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 컬렉션 아님 |
| 404 | COLLECTION_NOT_FOUND | 컬렉션 없음 |
| 404 | NOT_FOUND | 도서 없음 |
| 409 | ALREADY_IN_COLLECTION | 이미 컬렉션에 포함된 도서 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 8. 컬렉션에서 책 삭제

### 8.1 DELETE `/api/collections/{collection_id}/books/{book_id}`

- **설명:** 컬렉션에서 특정 도서 제거

#### 1. Request Syntax

```bash
curl -X DELETE "https://example.com/api/collections/1/books/101" \
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
| collection_id | integer \| string | Y | Path. 컬렉션 ID |
| book_id | integer \| string | Y | Path. 도서 ID |

#### 4. Response

**200 OK**

```json
{
  "collection_id": 1,
  "book_id": 101,
  "removed": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 컬렉션 아님 |
| 404 | COLLECTION_NOT_FOUND | 컬렉션 없음 |
| 404 | NOT_IN_COLLECTION | 컬렉션에 해당 도서가 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 9. 컬렉션 책 순서 변경

### 9.1 PUT `/api/collections/{collection_id}/books/order`

- **설명:** 컬렉션 내 전체 도서 순서 재정렬
- **규칙:** 요청한 `order`는 컬렉션의 전체 도서 ID 배열이어야 함

#### 1. Request Syntax

```bash
curl -X PUT "https://example.com/api/collections/1/books/order" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"order":[203,101,305]}'
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
| collection_id | integer \| string | Y | Path. 컬렉션 ID |
| order | array&lt;integer \| string&gt; | Y | 전체 순서 배열 |

#### 4. Response

**200 OK**

```json
{
  "updated": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | INVALID_ORDER | 누락/중복/존재하지 않는 book_id 포함, 전체 개수 불일치 |
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 컬렉션 아님 |
| 404 | COLLECTION_NOT_FOUND | 컬렉션 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 10. 데이터 소스/내부 로직 메모

- `collections`: 컬렉션 메타데이터 저장
- `collection_books`: 도서 연결, 순서(`order_index`) 및 추가 시각(`added_at`) 관리
- `books`: 상세/목록용 도서 제목/표지 조회 소스
- 목록 썸네일의 `cover_images`는 컬렉션 내 도서 표지 최대 3개 반환

