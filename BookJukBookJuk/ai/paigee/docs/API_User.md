## BookJuk User API 명세

**버전:** 1.0  
**최종 정리일:** 2026-03-27

이 문서는 BookJukBookJuk에서 사용하는 **User/팔로우/취향 분석 API**를 정리한 것이다.  
인증 세부 정책은 별도 문서를 따르고, 여기서는 내 프로필, 타인 프로필, 흥미로운 사실, 취향 분석, 팔로우 관련 엔드포인트를 다룬다.

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

## 1. 내 프로필 조회

### 1.1 GET `/api/me`

- **설명:** 현재 로그인 유저의 프로필/통계 조회

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/me" \
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
{
  "user_id": 1,
  "nickname": "최찬우",
  "profile_image_url": "https://cdn.example.com/profiles/1.jpg",
  "bio": "책과 커피를 좋아해요.",
  "stats": {
    "rated_count": 0,
    "review_count": 0,
    "collection_count": 0
  },
  "follower_count": 0,
  "following_count": 0
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 2. 내 프로필 수정

### 2.1 PUT `/api/me`

- **설명:** 내 프로필 정보 수정 (부분 수정 가능)

#### 1. Request Syntax

```bash
curl -X PUT "https://example.com/api/me" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"nickname":"책토끼","bio":"요즘은 고전 읽는 중"}'
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
| nickname | string | N | 닉네임 |
| profile_image_url | string | N | 프로필 이미지 URL |
| bio | string | N | 자기소개 |

#### 4. Response

**200 OK**

```json
{
  "user_id": 1,
  "nickname": "책토끼",
  "profile_image_url": "https://cdn.example.com/profiles/1-new.jpg",
  "bio": "요즘은 고전 읽는 중",
  "updated": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 409 | NICKNAME_ALREADY_EXISTS | 중복 닉네임 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 3. 프로필 공유용 URL 조회

### 3.1 GET `/api/me/share-url`

- **설명:** 내 프로필 공유 링크 조회

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/me/share-url" \
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
{
  "share_url": "https://앱도메인/users/1"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 4. 타인 프로필 조회

### 4.1 GET `/api/users/{user_id}`

- **설명:** 특정 유저 프로필 조회
- **인증:** 선택
  - 로그인: `is_following`, `taste_match_percent` 계산
  - 비로그인: `is_following=null`, `taste_match_percent=null`

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/users/2" \
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
{
  "user_id": 2,
  "nickname": "이동진",
  "profile_image_url": "https://cdn.example.com/profiles/2.jpg",
  "is_verified": true,
  "verified_label": "평론가",
  "stats": {
    "rated_count": 6114,
    "review_count": 2681,
    "collection_count": 0
  },
  "follower_count": 238964,
  "following_count": 1,
  "is_following": false,
  "taste_match_percent": 80
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 404 | NOT_FOUND | 유저 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 5. 타인 프로필 - 흥미로운 사실 조회

### 5.1 GET `/api/users/{user_id}/interesting-facts`

- **설명:** 로그인 유저와 대상 유저의 독서 취향 비교 결과 조회
- **인증:** 필수 (내 데이터와 비교 필요)
- **규칙:**
  - `both_enjoyed`: 둘 다 별점 4.0 이상
  - `both_might_like`: 한쪽만 평가했고 상대에게 벡터 유사도가 높은 책
  - `rating_clash`: 동일 책 별점 차이 2.0 이상

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/users/2/interesting-facts" \
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
| user_id | integer \| string | Y | Path. 대상 유저 ID |

#### 4. Response

**200 OK**

```json
{
  "both_enjoyed": [
    {
      "book_id": 101,
      "title": "데미안",
      "cover_image_url": "https://cdn.example.com/books/101.jpg",
      "my_score": 4.5,
      "their_score": 4.0
    }
  ],
  "both_might_like": [
    {
      "book_id": 203,
      "title": "소년이 온다",
      "cover_image_url": "https://cdn.example.com/books/203.jpg"
    }
  ],
  "rating_clash": [
    {
      "book_id": 305,
      "title": "예시 도서",
      "cover_image_url": "https://cdn.example.com/books/305.jpg",
      "my_score": 5.0,
      "their_score": 2.5
    }
  ]
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | NOT_FOUND | 대상 유저 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 6. 내 취향 분석 조회

### 6.1 GET `/api/me/taste-analysis`

- **설명:** 내 독서 취향 분석 리포트 조회
- **인증:** 필수
- **기반 데이터:** `ratings`, `book_vectors`, `book_user_states`

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/me/taste-analysis" \
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
{
  "avg_rating": 3.8,
  "total_rated": 42,
  "favorite_genres": [
    {
      "genre": "소설",
      "count": 18,
      "avg_score": 4.2
    }
  ],
  "favorite_keywords": [
    {
      "keyword": "성장",
      "weight": 0.82
    }
  ],
  "rating_distribution": {
    "5.0": 5,
    "4.5": 8,
    "4.0": 12,
    "3.5": 7
  },
  "fun_facts": [
    "상위 10% 평가자보다 평균 별점이 0.3 높아요",
    "가장 많이 읽은 장르는 한국 소설이에요"
  ],
  "generated_at": "2026-03-27T00:00:00Z"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | NOT_ENOUGH_DATA | 평가 데이터 5개 미만 |
| 401 | UNAUTHORIZED | 로그인 필요 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 7. 타인 취향 분석 조회

### 7.1 GET `/api/users/{user_id}/taste-analysis`

- **설명:** 특정 유저의 취향 분석 리포트 조회
- **인증:** 선택

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/users/2/taste-analysis" \
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
{
  "avg_rating": 4.1,
  "total_rated": 6114,
  "favorite_genres": [
    {
      "genre": "인문",
      "count": 1100,
      "avg_score": 4.4
    }
  ],
  "favorite_keywords": [
    {
      "keyword": "철학",
      "weight": 0.88
    }
  ],
  "rating_distribution": {
    "5.0": 1200,
    "4.5": 1700,
    "4.0": 1900
  },
  "fun_facts": [
    "평균보다 평점 분산이 낮아 일관된 취향을 보입니다."
  ],
  "generated_at": "2026-03-27T00:00:00Z"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 404 | NOT_FOUND | 대상 유저 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 8. 팔로우

### 8.1 POST `/api/users/{user_id}/follow`

- **설명:** 대상 유저 팔로우

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/users/2/follow" \
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
| user_id | integer \| string | Y | Path. 대상 유저 ID |

#### 4. Response

**200 OK**

```json
{
  "following": true
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | CANNOT_FOLLOW_SELF | 자기 자신 팔로우 시도 |
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | NOT_FOUND | 대상 유저 없음 |
| 409 | ALREADY_FOLLOWING | 이미 팔로우 중 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 9. 언팔로우

### 9.1 DELETE `/api/users/{user_id}/follow`

- **설명:** 대상 유저 언팔로우

#### 1. Request Syntax

```bash
curl -X DELETE "https://example.com/api/users/2/follow" \
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
| user_id | integer \| string | Y | Path. 대상 유저 ID |

#### 4. Response

**200 OK**

```json
{
  "following": false
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 404 | NOT_FOLLOWING | 팔로우 관계 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 10. 팔로워 목록

### 10.1 GET `/api/users/{user_id}/followers`

- **설명:** 대상 유저를 팔로우하는 유저 목록 조회
- **인증:** 선택

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/users/2/followers" \
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
    "user_id": 7,
    "nickname": "독서러버",
    "profile_image_url": "https://cdn.example.com/profiles/7.jpg",
    "is_verified": false,
    "is_following": true
  }
]
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 404 | NOT_FOUND | 대상 유저 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 11. 팔로잉 목록

### 11.1 GET `/api/users/{user_id}/following`

- **설명:** 대상 유저가 팔로우한 유저 목록 조회
- **인증:** 선택

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/users/2/following" \
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
    "user_id": 10,
    "nickname": "북콜렉터",
    "profile_image_url": "https://cdn.example.com/profiles/10.jpg",
    "is_verified": true,
    "is_following": false
  }
]
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 404 | NOT_FOUND | 대상 유저 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 12. 데이터 소스/스키마 메모

- `users`: 프로필 기본 정보
- `ratings`, `reviews`, `collections`: 프로필 통계 집계
- `book_vectors`, `book_user_states`: 취향 분석/유사도 기반 계산
- **신규 테이블 필요:** `follows(follower_id BIGINT, following_id BIGINT, created_at DATETIME, PK(follower_id, following_id))`
- **신규 컬럼 필요:** `users.is_verified`, `users.verified_label`
- `taste_match_percent`는 동일 도서 별점 벡터의 코사인 유사도 기반 내부 계산값

