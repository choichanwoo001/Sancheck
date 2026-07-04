"""북적북적 하이브리드 추천 엔진 CLI 진입점

독서 이력은 **항상 Supabase** (`ratings` / `shelves` / `book_user_states`)에서만 불러옵니다.
KG·임베딩은 DB에 영속된 경우 시작 시 로드합니다 (`HYBRID_PERSIST_KG` / `HYBRID_PERSIST_EMBEDDINGS`).

사전 준비 (KG·벡터가 비어 있으면 추천이 불가):
  1) `backend/scripts/seed_hybrid_recommender_e2e.py --isbn ...` 로 `books`(·캐시) 시드 (이력 책 ISBN 포함)
  2) `ai/build_hybrid_catalog.py` 로 **사용자 이력에 나온 ISBN** 기준 KG·`book_vectors` 구축 (`HYBRID_PERSIST_KG=1` 등)

필수 환경: 루트 `.env` 에 `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`(또는 ANON).
KG/벡터 DB 로드·영속은 `HYBRID_PERSIST_KG` / `HYBRID_PERSIST_EMBEDDINGS`(`.env.example` 참고).

사용자 식별: 인자 생략 시 `HYBRID_CLI_SUPABASE_USER_ID` 환경 변수, 둘 다 없으면
`dev_test_user_1`(시드 `seed_supabase_core_demo.py` 기본 `--user-id` 와 동일).

사용 예시:
    python hybrid_recommender_main.py

    python hybrid_recommender_main.py --supabase-user-id <다른 users.Key>

    python hybrid_recommender_main.py --load-dir ./saved_pipeline
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_AI_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _AI_DIR.parent
_env = _REPO_ROOT / ".env"
if _env.is_file():
    load_dotenv(_env)

sys.path.insert(0, str(_AI_DIR))

# `backend/scripts/seed_supabase_core_demo.py` 의 DEFAULT_DEV_USER_ID 와 맞춤 (단일 개발 사용자)
DEFAULT_SUPABASE_USER_ID = "dev_test_user_1"

from hybrid_recommender import HybridRecommenderPipeline
from hybrid_recommender.supabase_book_context import create_supabase_client_from_env
from hybrid_recommender.supabase_user_profile import load_user_profile_from_supabase


def _print_header() -> None:
    print("=" * 60)
    print("  북적북적 하이브리드 추천 엔진")
    print("  Knowledge Graph + RippleNet + MMR + XAI")
    print("=" * 60)
    print()


def _print_results(results: list) -> None:
    if not results:
        print("추천 결과가 없습니다.")
        return

    print(f"\n{'─' * 60}")
    print(f"  추천 도서 TOP {len(results)}")
    print(f"{'─' * 60}")

    for i, r in enumerate(results, 1):
        print(f"\n{i}. {r.title}")
        if r.authors:
            print(f"   저자: {r.authors}")
        if r.publisher:
            print(f"   출판사: {r.publisher} ({r.published_year})")
        if r.kdc_class:
            print(f"   분류: {r.kdc_class}")
        print(
            f"   점수: {r.final_score:.3f} "
            f"[그래프={r.graph_score:.3f} | 벡터={r.vector_score:.3f} | α={r.alpha_used:.2f}]"
        )
        if r.explanation:
            print(f"   설명: {r.explanation}")
        if r.kg_paths:
            for path in r.kg_paths[:1]:
                path_str = " → ".join(
                    f"{head}→{tail}" for head, rel, tail in path
                )
                print(f"   KG: {path_str}")

    print(f"\n{'─' * 60}\n")


def _exit(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _resolve_supabase_user_id(cli_value: str | None) -> str:
    """CLI > HYBRID_CLI_SUPABASE_USER_ID > DEFAULT_SUPABASE_USER_ID."""
    if cli_value and str(cli_value).strip():
        return str(cli_value).strip()
    env_uid = os.getenv("HYBRID_CLI_SUPABASE_USER_ID", "").strip()
    if env_uid:
        return env_uid
    return DEFAULT_SUPABASE_USER_ID


def _persist_kwargs_from_args(args: argparse.Namespace) -> dict:
    if args.persist_kg and args.no_persist_kg:
        _exit("[오류] --persist-kg 와 --no-persist-kg 는 함께 쓸 수 없습니다.")
    if args.persist_embeddings and args.no_persist_embeddings:
        _exit("[오류] --persist-embeddings 와 --no-persist-embeddings 는 함께 쓸 수 없습니다.")
    out: dict = {}
    if args.persist_kg:
        out["persist_kg"] = True
    elif args.no_persist_kg:
        out["persist_kg"] = False
    if args.persist_embeddings:
        out["persist_embeddings"] = True
    elif args.no_persist_embeddings:
        out["persist_embeddings"] = False
    return out


def _apply_supabase_user_profile(pipeline: HybridRecommenderPipeline, supabase_user_id: str) -> None:
    """`ratings` / `shelves` / `book_user_states` 를 읽어 `pipeline.user_profile` 을 덮어쓴다."""
    sb = pipeline.supabase_client or create_supabase_client_from_env()
    if not sb:
        _exit("[오류] Supabase 클라이언트가 없습니다. SUPABASE_URL 과 키를 확인하세요.")
    pipeline.user_profile = load_user_profile_from_supabase(sb, supabase_user_id)
    print(f"\n[사용자 이력] Supabase 사용자 {supabase_user_id} 로드")
    print(f"  {pipeline.user_profile.summary()}")


async def run_recommend(args: argparse.Namespace) -> None:
    """Supabase 사용자 이력만으로 추천 파이프라인을 실행한다."""
    _print_header()

    cli_uid = getattr(args, "supabase_user_id", None)
    env_uid = os.getenv("HYBRID_CLI_SUPABASE_USER_ID", "").strip()
    uid = _resolve_supabase_user_id(cli_uid)
    print(f"[사용자] Supabase 사용자 ID: {uid}")
    if not (cli_uid and str(cli_uid).strip()) and not env_uid:
        print(
            f"  (기본 {DEFAULT_SUPABASE_USER_ID} — 다른 사용자: "
            "--supabase-user-id 또는 HYBRID_CLI_SUPABASE_USER_ID)"
        )

    sb = create_supabase_client_from_env()
    if not sb:
        _exit(
            "[오류] Supabase 연결이 필요합니다. "
            "SUPABASE_URL 과 SUPABASE_SERVICE_ROLE_KEY(또는 ANON) 를 확인하세요."
        )

    persist_kw = _persist_kwargs_from_args(args)

    if args.load_dir:
        if not os.path.exists(args.load_dir):
            _exit(f"[오류] --load-dir 경로가 없습니다: {args.load_dir}")
        print(f"[로드] {args.load_dir}")
        pipeline = HybridRecommenderPipeline.from_env(
            user_id=uid,
            noise_threshold=args.noise_threshold,
            mmr_lambda=args.mmr_lambda,
            epsilon=args.epsilon,
            supabase_client=sb,
            use_supabase=True,
            **persist_kw,
        )
        pipeline.load(args.load_dir)
    else:
        pipeline = HybridRecommenderPipeline.from_env(
            user_id=uid,
            noise_threshold=args.noise_threshold,
            mmr_lambda=args.mmr_lambda,
            epsilon=args.epsilon,
            supabase_client=sb,
            use_supabase=True,
            **persist_kw,
        )
        print("[카탈로그] Supabase KG·book_vectors만 사용합니다 (add_books 생략).")

    if pipeline.kg.node_count() == 0 and len(pipeline.vector_store) == 0:
        _exit(
            "[오류] 로드된 KG/벡터가 없습니다. "
            "HYBRID_PERSIST_KG·HYBRID_PERSIST_EMBEDDINGS 로 DB에 구축했는지, 마이그레이션을 확인하세요."
        )

    _apply_supabase_user_profile(pipeline, uid)

    if pipeline.user_profile.action_count == 0:
        _exit(
            "[오류] 이 사용자에 대한 Supabase 이력(ratings / shelves / book_user_states)이 없습니다. "
            "DB에 데이터를 넣은 뒤 다시 실행하세요."
        )

    print(f"\n  {pipeline.user_profile.summary()}")

    verbose = bool(getattr(args, "verbose", False)) or os.getenv(
        "HYBRID_VERBOSE", ""
    ).strip().lower() in ("1", "true", "yes")

    print(f"\n[추천] top_k={args.top_k} 실행 중...")
    if verbose:
        print("  (--verbose / HYBRID_VERBOSE=1: 후보 수집·상위 점수 상세 출력)")
    results = await pipeline.recommend(
        top_k=args.top_k,
        with_explanation=not args.no_explanation,
        verbose=verbose,
    )

    _print_results(results)

    if args.save_dir:
        pipeline.save(args.save_dir)

    status = pipeline.status()
    print(f"파이프라인 상태: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="북적북적 하이브리드 추천 (Supabase 사용자 이력 전용)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--supabase-user-id",
        metavar="USER_KEY",
        default=None,
        help=(
            'Supabase 사용자 식별자 (public.users."Key" 등). '
            "생략 시 HYBRID_CLI_SUPABASE_USER_ID, 없으면 dev_test_user_1"
        ),
    )

    parser.add_argument("--top-k", type=int, default=5, help="추천 수 (기본 5)")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Phase 3 후보 수집 상세·상위 점수 출력 (또는 HYBRID_VERBOSE=1)",
    )
    parser.add_argument(
        "--no-explanation",
        action="store_true",
        help="LLM 설명 생성 비활성화 (빠른 실행)",
    )

    parser.add_argument("--noise-threshold", type=float, default=0.50,
                        help="KG 노이즈 필터 임계값 (기본 0.50)")
    parser.add_argument("--mmr-lambda", type=float, default=0.6,
                        help="MMR 관련성-다양성 균형 (기본 0.6)")
    parser.add_argument("--epsilon", type=float, default=0.15,
                        help="Epsilon-greedy 탐색률 (기본 0.15)")

    parser.add_argument("--save-dir", help="파이프라인 저장 경로")
    parser.add_argument("--load-dir", help="저장된 파이프라인 로드 후, 사용자 이력은 여전히 Supabase에서 로드")

    parser.add_argument(
        "--persist-kg",
        action="store_true",
        help="KG를 Supabase에 저장/시작 시 로드 (HYBRID_PERSIST_KG=1 과 동일)",
    )
    parser.add_argument(
        "--no-persist-kg",
        action="store_true",
        help="HYBRID_PERSIST_KG 가 있어도 KG DB 영속 비활성화",
    )
    parser.add_argument(
        "--persist-embeddings",
        action="store_true",
        help="임베딩을 book_vectors 에 저장 (HYBRID_PERSIST_EMBEDDINGS=1)",
    )
    parser.add_argument(
        "--no-persist-embeddings",
        action="store_true",
        help="HYBRID_PERSIST_EMBEDDINGS 가 있어도 임베딩 DB 동기화 비활성화",
    )

    args = parser.parse_args()
    asyncio.run(run_recommend(args))


if __name__ == "__main__":
    main()
