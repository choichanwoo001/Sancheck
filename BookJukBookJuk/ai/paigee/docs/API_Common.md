## BookJuk API Common 명세

**버전:** 1.0  
**최종 정리일:** 2026-03-27

이 문서는 BookJukBookJuk API 전반에서 공통으로 사용하는 **인증/에러/페이지네이션/날짜 포맷/Base URL 규칙**을 정리한 것이다.  
도메인별 상세 요청/응답은 각 API 문서(`API_Books.md`, `API_Shelf.md` 등)를 따른다.

---

## 1. 인증 방식

- **설명:** 인증이 필요한 엔드포인트는 아래 두 방식 중 하나로 접근한다.
  - 세션 쿠키
  - `Authorization: Bearer <app-session-token>`
- **비고:** 인증 불필요(또는 선택) 엔드포인트는 각 명세서에 별도 표기한다.

### 1.1 Request Header (공통)

| Header | 설명 | 필수 |
|--------|------|------|
| Cookie | 세션 쿠키 (인증된 경우) | Cookie 또는 Authorization 중 하나 필수 |
| Authorization | `Bearer <app-session-token>` | Cookie 또는 Authorization 중 하나 필수 |

---

## 2. 공통 에러 응답 포맷

- **설명:** 에러 발생 시 아래 JSON 포맷을 공통 사용한다.

```json
{
  "error": "ERROR_CODE",
  "message": "사람이 읽을 수 있는 에러 설명"
}
```

---

## 3. 공통 HTTP 상태코드

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | BAD_REQUEST | 요청 파라미터 오류 또는 누락 |
| 401 | UNAUTHORIZED | 미인증 또는 세션 만료 |
| 403 | FORBIDDEN | 권한 없음 (타인 리소스 접근 등) |
| 404 | NOT_FOUND | 리소스 없음 |
| 409 | CONFLICT | 중복 데이터 또는 상태 충돌 |
| 500 | INTERNAL_SERVER_ERROR | 서버 내부 오류 |
| 502 | UPSTREAM_ERROR | 외부 API(GitHub, 카카오, 알라딘 등) 호출 실패 |

---

## 4. 페이지네이션 공통 규칙

- **Query 파라미터**
  - `page`: 1-base, default=1
  - `per_page`: default=30
- **Response 규칙**
  - 페이지네이션이 적용되는 목록 응답은 `page`, `per_page`, `total_count`를 항상 포함한다.

예:

```json
{
  "items": [],
  "page": 1,
  "per_page": 30,
  "total_count": 0
}
```

---

## 5. 날짜 포맷

- 모든 날짜/시간 필드는 **ISO8601 UTC** 문자열을 사용한다.
- 예: `2026-03-27T10:00:00Z`

---

## 6. Base URL 목록

| 도메인 | Base URL | 문서 |
|--------|----------|------|
| 인증 | `/api/auth` | `API_Auth.md` |
| 도서 | `/api/books` | `API_Books.md` |
| 통합검색 | `/api/search` | `API_Books.md` |
| 보관함/별점 | `/api/shelf`, `/api/ratings` | `API_Shelf.md` |
| 리뷰/댓글 | `/api/reviews`, `/api/comments` | `API_Review.md` |
| 컬렉션 | `/api/collections` | `API_Collection.md` |
| 유저 | `/api/users`, `/api/me` | `API_User.md` |
| 챗봇 | `/api/chat` | `API_Chat.md` |

