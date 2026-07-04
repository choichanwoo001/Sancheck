## BookJuk Chat (Paige Agent) API 명세

**버전:** 1.0  
**최종 정리일:** 2026-03-27

이 문서는 BookJukBookJuk에서 사용하는 **Paige 대화 API**를 정리한 것이다.  
`Paige_agent_flow_docs.md`의 Intent/채널 구조를 기준으로 하며, 여기서는 세션 시작, 메시지 송수신, 히스토리 조회, 제안 수락만 다룬다.

---

### 공통 규칙

> 공통 요청 형식, 공통 에러 코드는 `API_Common.md` 참고.

- **Base URL:** `/api/chat`
- **인증:** 필수. 세션 쿠키 또는 `Authorization: Bearer <app-session-token>`
- **응답 방식:** 현재 명세는 JSON 기준. SSE 스트리밍은 추후 확장 가능
- **에러 응답 포맷(공통):**

```json
{
  "error": "ERROR_CODE",
  "message": "사람이 읽을 수 있는 에러 설명"
}
```

### Intent 정의 (v2)

- `state_change`
- `book_qna_collect`
- `review_assist`
- `review_nudge`
- `book_recommend`
- `smalltalk`

### 채널 정의

- `mypage`: 마이페이지 상단 Paige 챗봇 (일반 대화 + 모든 Intent)
- `book_detail`: 책 상세 "질문하기" 버튼 진입 (book_id 고정, `book_qna_collect` 중심)
- `store`: 서점 현장 채널 (명세만 제공, 추후 지원 예정)

### 코멘트 작성 유도 규칙

- Paige는 코멘트를 자동 작성/자동 게시하지 않는다.
- 코멘트 작성 유도는 아래 조건에서 활성화된다.
  - 같은 책 대화방 메시지(유저+AI) 5개 이상 누적
  - 또는 해당 책 별점 등록 상태(`RATED_ONLY`)
- 유도 응답에는 "지금까지 남긴 대화 요약 포인트"를 함께 제공한다.

---

## 1. 대화 세션 시작 또는 재진입

### 1.1 POST `/api/chat/sessions`

- **설명:** 채널/책 컨텍스트 기준 세션 시작 또는 기존 활성 세션 재진입
- **재진입 규칙:** 동일 `(user_id + source_channel + book_id)` 활성 세션 존재 시 기존 `session_id` 반환
- **신규 세션 규칙:** 세션 생성 후 트리거 우선순위를 계산해 Paige 첫 메시지 반환

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/chat/sessions" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"source_channel":"mypage"}'
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
| source_channel | string | Y | `mypage` \| `book_detail` \| `store` |
| book_id | integer \| string | N | `book_detail` 채널일 때 필수 |

#### 4. Response

**200 OK**

```json
{
  "session_id": "sess_abc123",
  "is_new": true,
  "room_type": "agent",
  "book_id": null,
  "paige_greeting": "오늘은 어떤 책 이야기부터 해볼까요?",
  "quick_actions": [
    "최근 읽은 책 이야기",
    "책 추천해줘",
    "코멘트 써볼래"
  ]
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 400 | MISSING_BOOK_ID | `book_detail` 채널인데 `book_id` 누락 |
| 400 | INVALID_SOURCE_CHANNEL | 지원하지 않는 source_channel |
| 401 | UNAUTHORIZED | 로그인 필요 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 2. 메시지 전송

### 2.1 POST `/api/chat/sessions/{session_id}/messages`

- **설명:** 사용자 메시지 전송 후 Paige 응답 생성
- **처리 흐름:**
  1. Intent 분류
  2. Tool 라우팅 (`Paige_agent_flow_docs.md` 섹션 10)
  3. 응답 생성 + quick action/action suggestion 구성
- **비고:** `review_assist`/`review_nudge` 응답은 완성 코멘트 대신 "작성 포인트" 중심으로 반환

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/chat/sessions/sess_abc123/messages" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"content":"이 책 어때?"}'
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
| session_id | string | Y | Path. 대화 세션 ID |
| content | string | Y | 사용자 메시지 |

#### 4. Response

**200 OK**

```json
{
  "message_id": "msg_xyz",
  "role": "ai",
  "intent": "review_nudge",
  "content": "이 책에 대해 대화를 많이 쌓았어요. 코멘트 한 줄 남겨보면 어때요?",
  "quick_actions": [
    "코멘트 직접 쓰기",
    "핵심 포인트 더 보기",
    "조금 더 대화하기"
  ],
  "context_points": [
    "주인공의 선택이 현실적으로 느껴졌다고 말함",
    "중반 전개가 가장 몰입됐다고 언급함",
    "결말이 여운이 남는다고 표현함"
  ],
  "action_suggestions": [
    {
      "type": "open_review_editor",
      "book_id": 5,
      "prefill_mode": "empty_with_points"
    }
  ],
  "created_at": "2026-03-27T10:00:00Z"
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 세션 아님 |
| 404 | SESSION_NOT_FOUND | 세션 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 3. 대화 히스토리 조회

### 3.1 GET `/api/chat/sessions/{session_id}/messages`

- **설명:** 세션의 대화 메시지 목록 조회 (본인만)

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/chat/sessions/sess_abc123/messages?page=1&per_page=30&sort=asc" \
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
| session_id | string | Y | Path. 대화 세션 ID |
| page | integer | N | 페이지 번호(1-base), default=1 |
| per_page | integer | N | 페이지당 메시지 수, default=30 |
| sort | string | N | `asc` 고정(기본값 asc) |

#### 4. Response

**200 OK**

```json
[
  {
    "message_id": "msg_1",
    "role": "user",
    "intent": null,
    "content": "오늘 뭐 읽으면 좋을까?",
    "created_at": "2026-03-27T10:00:00Z"
  },
  {
    "message_id": "msg_2",
    "role": "ai",
    "intent": "book_recommend",
    "content": "가볍게 읽기 좋은 책 2권 추천해볼게요.",
    "created_at": "2026-03-27T10:00:02Z"
  }
]
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 세션 아님 |
| 404 | SESSION_NOT_FOUND | 세션 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 4. 내 세션 목록 조회

### 4.1 GET `/api/chat/sessions`

- **설명:** 내 대화 세션 목록 조회

#### 1. Request Syntax

```bash
curl -X GET "https://example.com/api/chat/sessions?source_channel=mypage" \
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
| source_channel | string | N | `mypage` \| `book_detail` \| `store` |
| book_id | integer \| string | N | 특정 도서 세션 필터 |

#### 4. Response

**200 OK**

```json
[
  {
    "session_id": "sess_abc123",
    "room_type": "agent",
    "book_id": null,
    "book_title": null,
    "last_message": "오늘 가볍게 읽을 책 2권 가져왔어요.",
    "created_at": "2026-03-27T09:50:00Z"
  }
]
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 5. 코멘트 작성 포인트 조회

### 5.1 POST `/api/chat/sessions/{session_id}/comment-guidance`

- **설명:** 해당 세션/책 기준 코멘트 작성 포인트를 생성해 반환
- **원칙:** 자동 작성/자동 게시 금지. 실제 등록은 사용자가 `POST /api/books/{book_id}/reviews`로 직접 수행

#### 1. Request Syntax

```bash
curl -X POST "https://example.com/api/chat/sessions/sess_abc123/comment-guidance" \
  -H "Authorization: Bearer <app-session-token>" \
  -H "Content-Type: application/json" \
  -d '{}'
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
| session_id | string | Y | Path. 대화 세션 ID |

#### 4. Response

**200 OK**

```json
{
  "book_id": 5,
  "context_points": [
    "초반보다 후반이 더 좋았다고 말함",
    "문체가 담백해서 읽기 편했다고 언급함",
    "비슷한 분위기의 책을 더 찾고 싶다고 말함"
  ],
  "recommended_structure": [
    "어떤 부분이 기억에 남았는지",
    "왜 그렇게 느꼈는지",
    "한 줄 총평"
  ]
}
```

| 상태코드 | error | 발생조건 |
|----------|-------|----------|
| 401 | UNAUTHORIZED | 로그인 필요 |
| 403 | FORBIDDEN | 본인 세션 아님 |
| 404 | SESSION_NOT_FOUND | 세션 없음 |

> 공통 에러(400/401/403/404/500/502)는 공통 규칙 참고.

---

## 6. 데이터 소스/스키마 메모

- 대화 저장 테이블(확정):
  - `conversation_sessions(session_id, user_id, book_id, room_type, source_channel, created_at)`
  - `conversation_messages(message_id, session_id, role, content, intent, created_at)`
- `book_detail` 채널은 `book_id` 고정 컨텍스트로 `book_qna_collect` 중심 라우팅
- `mypage` 채널은 모든 Intent 가능, 트리거 우선순위 기반 첫 메시지 구성
- 코멘트는 작성 유도만 수행하고, 실제 문안 작성/게시는 사용자 주도
- `store` 채널은 현재 미구현이며 추후 지원 예정
- `action_suggestions`는 프론트에서 타입 기반 버튼 렌더링을 위한 구조화 필드
- `context_points`는 책별 분리 세션에서 누적된 대화 요약 포인트

