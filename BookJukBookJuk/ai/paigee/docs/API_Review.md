## BookJuk Review & Comments API 명세

**버전:** 1.0  
**최종 정리일:** 2026-03-27

이 문서는 BookJukBookJuk에서 사용하는 **코멘트/답글/좋아요/신고 API**를 정리한 것이다.  
인증/유저 프로필 등은 별도 문서를 따르고, 여기서는 책 코멘트 조회, 코멘트 CRUD, 답글 CRUD, 좋아요 토글, 신고만 다룬다.

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

### 용어 정의 (UI 기준)

- `코멘트` = `reviews` 테이블 (책에 대한 짧은 감상)
- `답글` = `comments` 테이블 (코멘트에 달리는 댓글)
- `좋아요` = `review_likes` 테이블 (코멘트에만 존재)

---

## 1. 책의 코멘트 목록 조회

### 1.1 GET `/api/books/{book_id}/reviews`

- **설명:** 특정 책의 코멘트 목록 조회
- **인증:** 선택
  - 로그인: `my_liked` true/false 반환
  - 비로그인: `my_liked` null 반환

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/books/101/reviews?sort=popular&page=1&per_page=20"
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
| sort | string | N | `popular` \| `recent`, default=popular |
| page | integer | N | 페이지 번호(1-base), default=1 |
| per_page | integer | N | 페이지당 항목 수, default=20 |

#### 4. Response

**200 OK**

```json
{
  "reviews": [
    {
      "review_id": 1,
      "user": {
        "user_id": 1,
        "nickname": "신채이",
        "profile_image_url": "https://cdn.example.com/profiles/1.jpg"
      },
      "book_rating": 3.5,
      "content": "사실 정말 좋은 책이라고...",
      "like_count": 61,
      "comment_count": 3,
      "created_at": "2026-03-27T10:00:00Z",
      "my_liked": false
    }
  ],
  "page": 1,
  "per_page": 20
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | INVALID_SORT | 지원하지 않는 sort 값 |
| 404 | NOT_FOUND | 도서 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 2. 코멘트 작성

### 2.1 POST `/api/books/{book_id}/reviews`

- **설명:** 특정 책에 코멘트 작성
- **규칙:**
  - 별점 없이도 작성 가능
  - 책당 유저 1개 코멘트 제한
  - 작성 성공 시 `book_user_states.shelf_state` -> `REVIEW_POSTED`

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/books/101/reviews" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"content":"읽고 나서 오래 남는 문장들이 많았어요."}'
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
| content | string | Y | 코멘트 본문 |

#### 4. Response

**201 Created**

```json
{
  "review_id": 91,
  "book_id": 101,
  "content": "읽고 나서 오래 남는 문장들이 많았어요.",
  "created_at": "2026-03-27T10:40:00Z"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | BAD_REQUEST | content 누락 또는 빈 문자열 |
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | NOT_FOUND | 도서 없음 |
| 409 | REVIEW_ALREADY_EXISTS | 동일 유저가 같은 책에 이미 코멘트 작성 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 3. 코멘트 수정

### 3.1 PUT `/api/reviews/{review_id}`

- **설명:** 내 코멘트 수정

#### 1. Request Syntax

```bash
curl -X PUT "https://example.com/api/reviews/91" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"content":"두 번째 읽었을 때 더 좋았습니다."}'
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
| review_id | integer \| string | Y | Path. 코멘트 ID |
| content | string | Y | 수정할 코멘트 본문 |

#### 4. Response

**200 OK**

```json
{
  "review_id": 91,
  "content": "두 번째 읽었을 때 더 좋았습니다.",
  "updated": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | BAD_REQUEST | content 누락 또는 빈 문자열 |
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 코멘트 아님 |
| 404 | NOT_FOUND | 코멘트 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 4. 코멘트 삭제

### 4.1 DELETE `/api/reviews/{review_id}`

- **설명:** 내 코멘트 삭제

#### 1. Request Syntax

```bash
curl -X DELETE "https://example.com/api/reviews/91" \
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
| review_id | integer \| string | Y | Path. 코멘트 ID |

#### 4. Response

**200 OK**

```json
{
  "review_id": 91,
  "removed": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 코멘트 아님 |
| 404 | NOT_FOUND | 코멘트 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 5. 코멘트 좋아요 토글

### 5.1 POST `/api/reviews/{review_id}/like`

- **설명:** 코멘트 좋아요 토글 (있으면 취소, 없으면 생성)

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/reviews/91/like" \
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
| review_id | integer \| string | Y | Path. 코멘트 ID |

#### 4. Response

**200 OK**

```json
{
  "liked": true,
  "like_count": 62
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | NOT_FOUND | 코멘트 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 6. 코멘트의 답글 목록 조회

### 6.1 GET `/api/reviews/{review_id}/comments`

- **설명:** 특정 코멘트의 답글 목록 조회
- **인증:** 선택

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/reviews/91/comments"
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | N |
| Authorization | `Bearer <app-session-token>` | N |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| review_id | integer \| string | Y | Path. 코멘트 ID |

#### 4. Response

**200 OK**

```json
[
  {
    "comment_id": 301,
    "user": {
      "user_id": 5,
      "nickname": "독서왕",
      "profile_image_url": "https://cdn.example.com/profiles/5.jpg"
    },
    "content": "저도 그 부분 좋았어요.",
    "created_at": "2026-03-27T11:00:00Z"
  }
]
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 404 | NOT_FOUND | 코멘트 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 7. 답글 작성

### 7.1 POST `/api/reviews/{review_id}/comments`

- **설명:** 코멘트에 답글 작성

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/reviews/91/comments" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"content":"저도 비슷하게 느꼈어요!"}'
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
| review_id | integer \| string | Y | Path. 코멘트 ID |
| content | string | Y | 답글 본문 |

#### 4. Response

**201 Created**

```json
{
  "comment_id": 301,
  "review_id": 91,
  "content": "저도 비슷하게 느꼈어요!",
  "created_at": "2026-03-27T11:05:00Z"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | BAD_REQUEST | content 누락 또는 빈 문자열 |
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | NOT_FOUND | 코멘트 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 8. 답글 삭제

### 8.1 DELETE `/api/comments/{comment_id}`

- **설명:** 내 답글 삭제

#### 1. Request Syntax

```bash
curl -X DELETE "https://example.com/api/comments/301" \
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
| comment_id | integer \| string | Y | Path. 답글 ID |

#### 4. Response

**200 OK**

```json
{
  "comment_id": 301,
  "removed": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 답글 아님 |
| 404 | NOT_FOUND | 답글 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 9. 신고

### 9.1 POST `/api/reports`

- **설명:** 코멘트/답글 신고 접수

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/reports" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"target_type":"review","target_id":91,"reason":"욕설/비방"}'
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
| target_type | string | Y | `review` \| `comment` |
| target_id | integer \| string | Y | 신고 대상 ID |
| reason | string | Y | 신고 사유 |

#### 4. Response

**201 Created**

```json
{
  "report_id": 1001,
  "message": "신고가 접수되었습니다."
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | BAD_REQUEST | 필수 필드 누락 |
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | NOT_FOUND | 신고 대상 없음 |
| 409 | ALREADY_REPORTED | 동일 유저가 같은 대상 중복 신고 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 10. 데이터 소스/내부 로직 메모

- `reviews`: 코멘트 본문/작성자/대상 도서 관리 (책당 유저 1개 제한)
- `comments`: 코멘트의 답글 관리
- `review_likes`: `(user_id, review_id)` PK 기반 좋아요 토글
- 프로필 클릭 후 유저 페이지 이동은 User 도메인(`API_User.md`)에서 처리

