#!/usr/bin/env python3
"""책 토론 채팅 CLI 진입점.

사용법:
  python book_chat_main.py                           # 인터랙티브 제목 입력
  python book_chat_main.py --isbn 9788937460470      # ISBN 으로 직접 선택
  python book_chat_main.py --title "데미안" --author "헤르만 헤세"
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_REPO = Path(__file__).resolve().parent.parent
_env = _REPO / ".env"
if _env.is_file():
    load_dotenv(_env)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from book_chat import create_session


def _print_divider(char: str = "─", width: int = 60) -> None:
    print(char * width)


async def main(args: argparse.Namespace) -> None:
    session = await create_session(
        isbn13=args.isbn,
        title=args.title,
        author=args.author,
    )

    _print_divider("═")
    print(f"  {session.ctx.title}")
    if session.ctx.authors:
        print(f"  저자: {session.ctx.authors}")
    if session.ctx.publisher or session.ctx.published_year:
        print(f"  출판사: {session.ctx.publisher or '미상'} / {session.ctx.published_year or '미상'}")
    if session.ctx.kdc_class:
        print(f"  분류: {session.ctx.kdc_class}")
    _print_divider("═")
    print("책에 관해 자유롭게 질문하세요. (종료: q 또는 quit)\n")
    print("  예시 질문:")
    print("  - 이 책의 핵심 주제는 무엇인가요?")
    print("  - 주인공의 내적 갈등을 어떻게 해석할 수 있나요?")
    print("  - 작가가 이 책을 쓴 의도는 무엇인가요?")
    print("  - 시대적 배경이 이야기에 어떤 영향을 주나요?")
    _print_divider()
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n대화를 종료합니다.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("q", "quit", "exit", "종료"):
            print("대화를 종료합니다.")
            break

        if user_input.lower() in ("reset", "초기화"):
            session.reset_history()
            print("대화 히스토리를 초기화했습니다.\n")
            continue

        answer = await session.chat(user_input)
        print(f"\nBot: {answer}\n")
        _print_divider("·")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="책 토론 채팅 CLI")
    parser.add_argument("--isbn", default=None, help="ISBN-13 번호")
    parser.add_argument("--title", default=None, help="책 제목")
    parser.add_argument("--author", default=None, help="저자 이름")
    parsed = parser.parse_args()

    if not parsed.isbn and not parsed.title:
        print("책 제목 또는 ISBN 을 입력하세요.")
        parsed.title = input("책 제목: ").strip()
        if not parsed.title:
            print("제목을 입력하지 않았습니다. 종료합니다.")
            sys.exit(1)

    asyncio.run(main(parsed))
