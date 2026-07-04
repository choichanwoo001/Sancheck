"""FastAPI: 표지 프록시, 하이브리드 추천, 책 조회 API."""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from backend.routers.books import router as books_router
from backend.routers.collections import router as collections_router
from backend.routers.sections import router as sections_router

ROOT = Path(__file__).resolve().parent.parent
_AI_DIR = ROOT / "ai"
if str(_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_DIR))
_env = ROOT / ".env"
if _env.is_file():
    load_dotenv(_env)

app = FastAPI(title="BookJukBookJuk API", version="0.1.0")
app.include_router(books_router)
app.include_router(sections_router)
app.include_router(collections_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
