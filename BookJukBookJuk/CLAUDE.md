# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**BookJukBookJuk (책국책국)** — "A moment to get closer to books." A mobile web app combining social book discovery, AI-powered recommendations, and an intelligent reading assistant named **Paige**.

The core design document is `ai/paigee/docs/Paigee_agent_flow_docs.md` — read it before working on Paige.

## Rules

- **Never read `.env` files.** If `.env` values need to be set, describe what value to use and let the user update the file directly.
- **Frontend styling:** Never hardcode text sizes or palette colors. Use CSS custom properties from `frontend/src/styles/tokens.css`. Palette: `#92C7CF`, `#AAD7D9`, `#FBF9F1`, `#E5E1DA`. Use semantic variables like `var(--color-text-primary)`, `var(--color-brand-primary)`, `var(--font-size-base)`, and utility classes (`.text-title`, `.text-body`, `.text-caption`, `.text-muted`). If a new token is needed, add it to `tokens.css` first.

## Commands

### Frontend (React 18 + Vite)
```bash
cd frontend
npm install
npm run dev       # Dev server at http://localhost:3000
npm run build     # Output to dist/
npm run preview   # Preview production build
```

No linter, formatter, or test runner is configured for the frontend.

### Backend AI (Python)
```bash
pip install -r requirements.txt
cd ai

# 레거시 클러스터링 기반 취향 분석 CLI는 제거됨. 요약: docs/legacy_taste_analysis.md

# Book Q&A chat
python book_chat_main.py --isbn 9788937460470
python book_chat_main.py --title "데미안" --author "헤르만 헤세"

# Hybrid recommender — KG·벡터 최초 구축: books 시드 후, 사용자 이력 ISBN으로 구축
#   python backend/scripts/seed_hybrid_recommender_e2e.py --isbn <ISBN...>
#   cd ai && python build_hybrid_catalog.py
# Supabase 앱 코어 시드 (full_schema 마이그레이션 적용 후; 기본 단일 users_id=dev_test_user_1, 책 ~18권):
#   python backend/scripts/seed_supabase_core_demo.py --replace
# 추천 실행 (Supabase 이력; 기본 사용자 dev_test_user_1)
python hybrid_recommender_main.py
python hybrid_recommender_main.py --supabase-user-id <users.Key> --load-dir ./saved_pipeline
```

No test suite or linter is configured for the AI modules.

### Required Environment Variables (see repository root `.env.example`)
- `OPENAI_API_KEY` — Required by all AI modules
- `LIBRARY_API_KEY` — 정보나루 Korean Library API (book chat, recommender, 시드 스크립트)
- `ALADIN_API_KEY` — Aladin TTB book metadata API (book chat)
- `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (or anon where appropriate) — Book metadata / hybrid recommender `HYBRID_USE_SUPABASE`; `HYBRID_PERSIST_KG=1` → KG tables + (by default) `HYBRID_PERSIST_EMBEDDINGS` → `book_vectors` upsert/load
- `PINECONE_API_KEY/PINECONE_INDEX_NAME` — Optional; falls back to numpy in-memory vectors

## Architecture

### Integration Status

`backend/main.py` (FastAPI): `GET /api/book-cover`, `GET /api/recommendations` (하이브리드 파이프라인; Supabase KG·벡터·사용자 이력 필요). Vite dev는 `/api`를 백엔드로 프록시. 홈 「취향 저격」행은 성공 시 이 API로 채우고, 실패 시 `dummyBooks` 폴백.

채팅·기타 화면은 여전히 mock/스텁이 많음.

### Frontend (`frontend/src/`)
React SPA with React Router v6 (`App.jsx` defines all routes). State management via React hooks only (no Redux/Context). Pages: Home, Library, MyPage, BookDetail, BookChat, Search, Login, CollectionDetail, TasteAnalysisDetail, CommentDetail. `MyChat.jsx` is the Paige chatbot on MyPage; `BookChat.jsx` is the book-specific Q&A page. Uses Leaflet (`react-leaflet`) for bookstore maps.

### AI Backend (`ai/`)
Core deps: OpenAI (gpt-4o-mini / gpt-4o), LangChain, PyTorch (RippleNet GNN), scikit-learn, NetworkX.

1. **library_api** (`library_api/`) — 정보나루(data4library.kr) 도서·키워드 API (book_chat, hybrid, 시드 스크립트에서 사용).

2. **Book Chat** (`book_chat/`, entry: `book_chat_main.py`) — Hybrid retrieval QA for a specific book. Pipeline: `data_collector` → `graph_builder` (KG) + `vector_store` (embeddings) → `retriever` (graph + vector blend) → `chat_engine` (LLM with relevance guard).

3. **Hybrid Recommender** (`hybrid_recommender/`, entry: `hybrid_recommender_main.py`, HTTP는 `backend/main.py`) — 4-phase pipeline:
   - Phase 1 (`phase1_kg/`): LLM entity extraction → KG build (NetworkX in-memory) → noise filter; optional `HYBRID_PERSIST_KG` → `kg_nodes`/`kg_edges`; book metadata via `HYBRID_USE_SUPABASE`
   - Phase 2 (`phase2_model/`): OpenAI embeddings + RippleNet GNN, cold-start handling, Pinecone or numpy storage
   - Phase 3 (`phase3_scoring/`): User profile tracking, hybrid score = α·Graph + (1-α)·Vector with time decay
   - Phase 4 (`phase4_xai/`): MMR diversity, ε-greedy exploration, LLM-generated explanations

### Paige Agent (`ai/paigee/`) — In Development
Design complete; implementation pending. Key concepts:

- **Channels:** MyPage chatbot (primary), Book Detail Q&A button, Bookstore channel (future)
- **Shared core:** All channels route through the same `Paige Core Orchestrator` — only `Channel Adapter` differs
- **Intents:** `state_change`, `book_qna_collect`, `review_assist`, `review_nudge`, `book_recommend`, `smalltalk`
- **State model:** `LIST → READING → RATED_ONLY → REVIEW_POSTED`
- **Key principle:** Paige *proposes* reviews/comments; it never auto-posts. Final submission is always user-triggered.
- **DB:** SQLite — tables: `users`, `books`, `book_user_states`, `ratings`, `comments`, `comment_suggestions`, `conversation_sessions`, `conversation_events`
- **Trigger priority** (MyPage): chat context ready (score 100) > rated without comment (60–80) > store followup (60) > recommend window (40) > default greeting (10)
