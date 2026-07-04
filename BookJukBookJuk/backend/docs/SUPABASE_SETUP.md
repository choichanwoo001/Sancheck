# Supabase 연동 (책 카탈로그)

프론트는 `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`가 있고 `books` 테이블에 데이터가 있으면 **Supabase를 우선** 사용하고, 없거나 실패 시 `frontend/src/data/booksCatalog.json`으로 폴백합니다.

## 1. Supabase 프로젝트 생성

1. [supabase.com](https://supabase.com)에서 New project
2. Database password 저장
3. 프로젝트가 준비될 때까지 대기

## 2. SQL 적용

1. 대시보드 → **SQL Editor** → New query
2. 저장소의 `backend/supabase/migrations/20260425120000_bookjuk_full_schema.sql` 내용을 붙여 넣고 **Run**
3. **Database** → **Extensions**에서 `vector`·`pgcrypto`가 켜져 있는지 확인 (마이그레이션에 `create extension` 포함)

## 3. API 키 복사

**Project Settings → API**

| 용도 | 변수명 | 비고 |
|------|--------|------|
| React (브라우저) | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | **anon public** 만 사용 |
| 시드 스크립트 (로컬) | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | **service_role** 은 절대 프론트·Git에 넣지 말 것 |

## 4. 프론트 환경 변수

`frontend/.env` 파일을 만들고 (`.env.example` 참고):

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

저장 후 `npm run dev` 재시작.

## 5. 데이터 올리기 (시드)

정보나루에서 섹터별로 모은 뒤(기본 `--per-sector 50`) 아동·교육·그림책 등은 `backend/scripts/book_catalog_filters.py` 규칙으로 걸러 **Supabase에만** 반영하려면 `python backend/scripts/sync_supabase_books_from_api.py` 를 쓰면 됩니다.

Python 시드·동기화 스크립트는 **저장소 루트 `.env`**에 `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `LIBRARY_API_KEY` 등을 두고 읽습니다 (프론트용 `frontend/.env`의 `VITE_*`와는 파일이 다를 수 있음).

저장소 루트에서 (또는 가상환경에서):

```bash
pip install -r requirements.txt
```

PowerShell 예시 (값은 본인 프로젝트로 교체):

```powershell
$env:SUPABASE_URL="https://xxxx.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="서비스롤_시크릿"
python backend/scripts/seed_supabase_books.py
```

기본 입력 파일은 `frontend/src/data/booksCatalog.json`입니다. 다른 JSON을 쓰려면:

```bash
python backend/scripts/seed_supabase_books.py path/to/books.json
```

로컬 폴백 JSON을 Supabase와 맞추려면 `python backend/scripts/export_books_catalog.py` 로 `public.books` 를 내려받습니다 (서비스 롤 키 필요).

## 6. GraphQL (선택)

대시보드에서 **pg_graphql** / GraphQL 관련 메뉴(문서: [GraphQL](https://supabase.com/docs/guides/graphql))을 따라 엔드포인트를 켭니다. 현재 React 코드는 **PostgREST( supabase-js )**만 사용합니다.

## 7. 임베딩 컬럼

`books.embedding` 은 `vector(1536)` nullable입니다. 값은 앱/배치에서 OpenAI 등으로 생성 후 UPDATE 하면 됩니다. IVFFlat 인덱스는 데이터가 충분히 쌓인 뒤 마이그레이션 주석을 해제해 튜닝하세요.

## 문제 해결

- **항상 로컬 JSON만 보인다**: `books` 테이블이 비었거나 RLS/키 오류 → 시드 실행 또는 SQL에서 `books_select_public` 정책 확인
- **CORS/네트워크 오류**: URL이 프로젝트와 일치하는지, anon 키인지 확인
