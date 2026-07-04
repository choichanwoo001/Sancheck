## BookJuk Auth API 명세

**버전:** 1.0  
**최종 정리일:** 2026-03-27

이 문서는 BookJukBookJuk에서 사용하는 **인증/인가 API**를 정리한 것이다.  
회원가입, 로그인(세션), 로그아웃, 카카오 OAuth(예정)만 다룬다.

---

### 공통 규칙

> 공통 요청 형식, 공통 에러 코드 및 에러 응답 포맷은 `API_Common.md` 참고.

- **Base URL:** `/api/auth`
- **인증이 필요한 엔드포인트:** Cookie 또는 `Authorization: Bearer <app-session-token>` 중 하나
- **인증이 불필요한 엔드포인트:** `register`, `login`, `kakao` 관련 (아래 각 절에 명시)

### 관련 DB

- `users`: `Key`(PK, 사용자 ID), `username`, `password`, `nickname`, 프로필 필드, `created_at`

---

## 1. 회원가입

### 1.1 POST `/api/auth/register`

- **설명:** 신규 사용자 등록

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"reader01","password":"secret1234","nickname":"책토끼"}'
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Content-Type | `application/json` | Y |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| username | string | Y | 로그인 아이디 |
| password | string | Y | 비밀번호 |
| nickname | string | Y | 닉네임 |

#### 4. Response

**201 Created**

```json
{
  "user_id": "usr_01HZX...",
  "nickname": "책토끼",
  "created_at": "2026-03-27T10:00:00Z"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 409 | USERNAME_ALREADY_EXISTS | 동일 username 이미 존재 |

> 공통 에러(400/401/403/404/500/502)는 `API_Common.md` 참고.

---

## 2. 로그인

### 2.1 POST `/api/auth/login`

- **설명:** 로그인 성공 시 세션 쿠키 발급
- **인증:** 불필요

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"reader01","password":"secret1234"}' \
  -c cookies.txt
```

#### 2. Request Header

| Header | 설명 | 필수 |
|--------|------|------|
| Content-Type | `application/json` | Y |

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| username | string | Y | 로그인 아이디 |
| password | string | Y | 비밀번호 |

#### 4. Response

**200 OK**

- **Response Header:** `Set-Cookie`로 세션 쿠키 발급 (쿠키 이름·속성은 서버 구현에 따름)

```json
{
  "user_id": "usr_01HZX...",
  "nickname": "책토끼"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | INVALID_CREDENTIALS | 아이디/비밀번호 불일치 |

> 공통 에러(400/401/403/404/500/502)는 `API_Common.md` 참고.

---

## 3. 로그아웃

### 3.1 POST `/api/auth/logout`

- **설명:** 현재 세션 무효화 및 세션 쿠키 만료
- **인증:** 필요 (Cookie 또는 Bearer)

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/auth/logout" \
  -H "Authorization: Bearer <app-session-token>" \
  -b cookies.txt
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

- **Response Header:** `Set-Cookie`로 세션 쿠키 만료(삭제) 처리

```json
{
  "message": "로그아웃 되었습니다."
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 미인증 또는 세션 만료 |

> 공통 에러(400/401/403/404/500/502)는 `API_Common.md` 참고.

---

## 4. 카카오 OAuth 시작 (예정)

### 4.1 GET `/api/auth/kakao`

- **설명:** 카카오 로그인 동의 화면으로 리다이렉트
- **인증:** 불필요
- **비고:** 현재 미구현. 추후 지원 예정

#### 1. Request Syntax

```bash
curl -I "https://example.com/api/auth/kakao"
```

#### 2. Request Header

- 특별한 헤더 없음.

#### 3. Request Element

- Path/Query/Body 없음.

#### 4. Response

**302 Found**

- **Response Header:** `Location: https://kauth.kakao.com/oauth/authorize?client_id=...&redirect_uri=...&response_type=code&...`

---

## 5. 카카오 OAuth 콜백 (예정)

### 5.1 GET `/api/auth/kakao/callback`

- **설명:** 카카오 인가 코드로 토큰 교환 후 세션 발급, 앱 메인으로 리다이렉트
- **인증:** 불필요 (콜백은 카카오 리다이렉트로 진입)
- **비고:** 현재 미구현. 추후 지원 예정

#### 1. Request Syntax

```bash
curl -I "https://example.com/api/auth/kakao/callback?code=KAKAO_AUTH_CODE"
```

#### 2. Request Header

- 특별한 헤더 없음.

#### 3. Request Element

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| code | string | Y | Query. 카카오 인가 코드 |

#### 4. Response

**302 Found**

- **Response Header:** `Location: /` (앱 메인 등 클라이언트 기준 랜딩 URL)

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 502 | KAKAO_UPSTREAM_ERROR | 카카오 토큰/사용자 정보 API 호출 실패 |

> 공통 에러(400/401/403/404/500/502)는 `API_Common.md` 참고.
