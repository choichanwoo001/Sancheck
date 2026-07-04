## BookJuk API Index

**버전:** 1.0  
**최종 정리일:** 2026-03-27  
BookJukBookJuk 전체 API를 도메인별로 한눈에 확인할 수 있는 마스터 목록 문서.

---

## 1. Auth

| Method | Path | 설명 | 인증 | 문서 |
|--------|------|------|------|------|
| POST | `/api/auth/register` | 회원가입 | ❌ | `API_Auth.md` |
| POST | `/api/auth/login` | 로그인 (세션 쿠키 발급) | ❌ | `API_Auth.md` |
| POST | `/api/auth/logout` | 로그아웃 | ✅ | `API_Auth.md` |
| GET | `/api/auth/kakao` | 카카오 OAuth 시작 (예정) | ❌ | `API_Auth.md` |
| GET | `/api/auth/kakao/callback` | 카카오 OAuth 콜백 (예정) | ❌ | `API_Auth.md` |

---

## 2. Books

| Method | Path | 설명 | 인증 | 문서 |
|--------|------|------|------|------|
| GET | `/api/books/feed` | 홈 피드 조회 | 선택 | `API_Books.md` |
| GET | `/api/books/feed/{section_type}` | 홈 섹션 전체보기 | 선택 | `API_Books.md` |
| GET | `/api/search` | 통합 검색 (책/작가/컬렉션/유저) | 선택 | `API_Books.md` |
| GET | `/api/books/{book_id}` | 책 상세 조회 | 선택 | `API_Books.md` |
| GET | `/api/books/{book_id}/nearby-stores` | 근처 서점 조회 | ❌ | `API_Books.md` |

---

## 3. Shelf & Ratings

| Method | Path | 설명 | 인증 | 문서 |
|--------|------|------|------|------|
| GET | `/api/shelf` | 보관함 목록 조회 | ✅ | `API_Shelf.md` |
| POST | `/api/shelf` | 보관함 추가/변경 | ✅ | `API_Shelf.md` |
| DELETE | `/api/shelf/{book_id}` | 보관함 삭제 | ✅ | `API_Shelf.md` |
| PUT | `/api/ratings/{book_id}` | 별점 등록/수정 | ✅ | `API_Shelf.md` |
| DELETE | `/api/ratings/{book_id}` | 별점 삭제 | ✅ | `API_Shelf.md` |
| GET | `/api/shelf/shopping-list` | 쇼핑리스트 조회 (스마트카트) | ✅ | `API_Shelf.md` |

---

## 4. Review & Comments

| Method | Path | 설명 | 인증 | 문서 |
|--------|------|------|------|------|
| GET | `/api/books/{book_id}/reviews` | 책의 코멘트 목록 조회 | 선택 | `API_Review.md` |
| POST | `/api/books/{book_id}/reviews` | 코멘트 작성 | ✅ | `API_Review.md` |
| PUT | `/api/reviews/{review_id}` | 코멘트 수정 | ✅ | `API_Review.md` |
| DELETE | `/api/reviews/{review_id}` | 코멘트 삭제 | ✅ | `API_Review.md` |
| POST | `/api/reviews/{review_id}/like` | 코멘트 좋아요 토글 | ✅ | `API_Review.md` |
| GET | `/api/reviews/{review_id}/comments` | 답글 목록 조회 | 선택 | `API_Review.md` |
| POST | `/api/reviews/{review_id}/comments` | 답글 작성 | ✅ | `API_Review.md` |
| DELETE | `/api/comments/{comment_id}` | 답글 삭제 | ✅ | `API_Review.md` |
| POST | `/api/reports` | 신고 | ✅ | `API_Review.md` |

---

## 5. Collection

| Method | Path | 설명 | 인증 | 문서 |
|--------|------|------|------|------|
| GET | `/api/collections` | 내 컬렉션 목록 조회 | ✅ | `API_Collection.md` |
| GET | `/api/users/{user_id}/collections` | 특정 유저 컬렉션 목록 | 선택 | `API_Collection.md` |
| GET | `/api/collections/{collection_id}` | 컬렉션 상세 조회 | 선택 | `API_Collection.md` |
| POST | `/api/collections` | 컬렉션 생성 | ✅ | `API_Collection.md` |
| PUT | `/api/collections/{collection_id}` | 컬렉션 수정 | ✅ | `API_Collection.md` |
| DELETE | `/api/collections/{collection_id}` | 컬렉션 삭제 | ✅ | `API_Collection.md` |
| POST | `/api/collections/{collection_id}/books` | 컬렉션에 책 추가 | ✅ | `API_Collection.md` |
| DELETE | `/api/collections/{collection_id}/books/{book_id}` | 컬렉션에서 책 삭제 | ✅ | `API_Collection.md` |
| PUT | `/api/collections/{collection_id}/books/order` | 책 순서 변경 | ✅ | `API_Collection.md` |

---

## 6. User

| Method | Path | 설명 | 인증 | 문서 |
|--------|------|------|------|------|
| GET | `/api/me` | 내 프로필 조회 | ✅ | `API_User.md` |
| PUT | `/api/me` | 내 프로필 수정 | ✅ | `API_User.md` |
| GET | `/api/me/share-url` | 프로필 공유 URL | ✅ | `API_User.md` |
| GET | `/api/me/taste-analysis` | 내 취향 분석 | ✅ | `API_User.md` |
| GET | `/api/users/{user_id}` | 타인 프로필 조회 | 선택 | `API_User.md` |
| GET | `/api/users/{user_id}/taste-analysis` | 타인 취향 분석 | 선택 | `API_User.md` |
| GET | `/api/users/{user_id}/interesting-facts` | 흥미로운 사실 (취향 비교) | ✅ | `API_User.md` |
| POST | `/api/users/{user_id}/follow` | 팔로우 | ✅ | `API_User.md` |
| DELETE | `/api/users/{user_id}/follow` | 언팔로우 | ✅ | `API_User.md` |
| GET | `/api/users/{user_id}/followers` | 팔로워 목록 | 선택 | `API_User.md` |
| GET | `/api/users/{user_id}/following` | 팔로잉 목록 | 선택 | `API_User.md` |

---

## 7. Chat (Paige AI)

| Method | Path | 설명 | 인증 | 문서 |
|--------|------|------|------|------|
| POST | `/api/chat/sessions` | 세션 시작 또는 재진입 | ✅ | `API_Chat.md` |
| POST | `/api/chat/sessions/{session_id}/messages` | 메시지 전송 | ✅ | `API_Chat.md` |
| GET | `/api/chat/sessions/{session_id}/messages` | 대화 히스토리 조회 | ✅ | `API_Chat.md` |
| GET | `/api/chat/sessions` | 내 세션 목록 조회 | ✅ | `API_Chat.md` |
| POST | `/api/chat/sessions/{session_id}/comment-guidance` | 코멘트 작성 포인트 조회 | ✅ | `API_Chat.md` |

---

## 8. 전체 집계

- 총 엔드포인트 수: **57**
  - Auth 5
  - Books 5
  - Shelf & Ratings 6
  - Review & Comments 9
  - Collection 9
  - User 11
  - Chat 5

---

## 9. DB 추가/정리 필요 사항

- `follows` 테이블 신규:
  - `(follower_id, following_id, created_at)`
- `users` 테이블 컬럼 추가:
  - `is_verified`
  - `verified_label`
- 테이블명 확정:
  - `Untitled` -> `conversation_sessions`
  - `Untitled2` -> `conversation_messages`
- 복합 PK 추가 필요:
  - `ratings`
  - `book_user_states`
  - `shelf_books`
  - `collection_books`
  - `review_likes`
  - `book_authors`
- 모든 테이블 PK 타입 `BIGINT` 통일 필요

