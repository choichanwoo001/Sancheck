"""Supabase 코어 데모 시드 (bookjuk_full_schema DDL).

- public.books 는 INSERT 하지 않고, 기존 행에서 id·메타를 읽어 authors/book_authors·리뷰 등을 파생한다.
- kg_*, book_vectors, books.embedding 은 건드리지 않는다.

기본은 **단일 테스트 유저 `dev_test_user_1`** 한 명과 책 약 18권(10~20권 권장)이다.
`build_hybrid_catalog.py` / `hybrid_recommender_main.py` 의 기본 Supabase 사용자와 맞춘다.

환경: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (권장)

  python backend/scripts/seed_supabase_core_demo.py
  python backend/scripts/seed_supabase_core_demo.py --replace
  python backend/scripts/seed_supabase_core_demo.py --replace --user-id dev_test_user_1 --book-sample-size 18

다중 데모 유저(`demo_core_u_01` …)가 필요하면: `--users 2` 이상 (이때 `--user-id` 는 무시됨).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
REPO = _SCRIPTS.parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

SEED_PREFIX = "demo_core"
DEFAULT_DEV_USER_ID = "dev_test_user_1"
BOOK_SAMPLE_DEFAULT = 18
BOOK_SAMPLE_MIN = 10
BOOK_SAMPLE_MAX = 20
SHELF_TYPES = ("평가한", "읽은", "읽는중", "쇼핑리스트")
SHELF_SLUGS = {
    "평가한": "rated",
    "읽은": "read",
    "읽는중": "reading",
    "쇼핑리스트": "wish",
}


def _load_env() -> None:
    if not load_dotenv:
        return
    p = REPO / ".env"
    if p.is_file():
        load_dotenv(p)


def _create_client():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        print("[오류] SUPABASE_URL 및 SUPABASE_SERVICE_ROLE_KEY 가 필요합니다.", file=sys.stderr)
        raise SystemExit(1)
    try:
        from supabase import create_client

        return create_client(url, key)
    except Exception as e:
        print(f"[오류] Supabase 클라이언트 생성 실패: {e}", file=sys.stderr)
        raise SystemExit(1)


def _norm_author_token(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def parse_authors_field(authors: str) -> list[str]:
    if not (authors or "").strip():
        return []
    raw = authors.strip()
    parts = re.split(r"[,，、·/|]+", raw)
    out: list[str] = []
    for p in parts:
        n = _norm_author_token(p)
        if n and len(n) <= 200:
            out.append(n)
    if not out and raw:
        out.append(_norm_author_token(raw))
    return out


def author_id_from_name(name: str) -> str:
    n = _norm_author_token(name).lower()
    h = hashlib.sha256(n.encode("utf-8")).hexdigest()[:20]
    return f"{SEED_PREFIX}_a_{h}"


def clip_text(s: str, max_len: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def review_body_from_book(meta: dict[str, str]) -> str:
    title = (meta.get("title") or "").strip()
    desc = (meta.get("description") or "").strip()
    ed = (meta.get("editorial_review") or "").strip()
    base = desc or ed or ""
    if base:
        return clip_text(f"《{title}》 — {base}", 2000) if title else clip_text(base, 2000)
    return clip_text(f"《{title}》 읽기 좋았습니다." if title else "좋은 책이었습니다.", 500)


def _delete_demo_rows(supabase, dry_run: bool) -> None:
    if dry_run:
        print("[dry-run] 기존 demo_core 데이터 삭제 생략")
        return
    # 자식 → 부모 순 (FK)
    supabase.table("conversation_messages").delete().like("conversation_messages_id", f"{SEED_PREFIX}%").execute()
    supabase.table("conversation").delete().like("conversation_id", f"{SEED_PREFIX}%").execute()
    supabase.table("review_likes").delete().like("reviews_id", f"{SEED_PREFIX}%").execute()
    supabase.table("review_likes").delete().like("users_id", f"{SEED_PREFIX}%").execute()
    supabase.table("comments").delete().like("comments_id", f"{SEED_PREFIX}%").execute()
    supabase.table("reviews").delete().like("reviews_id", f"{SEED_PREFIX}%").execute()
    supabase.table("collection_books").delete().like("collections_id", f"{SEED_PREFIX}%").execute()
    supabase.table("collections").delete().like("collections_id", f"{SEED_PREFIX}%").execute()
    supabase.table("shelf_books").delete().like("shelves_id", f"{SEED_PREFIX}%").execute()
    supabase.table("book_user_states").delete().like("users_id", f"{SEED_PREFIX}%").execute()
    supabase.table("ratings").delete().like("users_id", f"{SEED_PREFIX}%").execute()
    supabase.table("shelves").delete().like("shelves_id", f"{SEED_PREFIX}%").execute()
    supabase.table("book_authors").delete().like("authors_id", f"{SEED_PREFIX}%").execute()
    supabase.table("authors").delete().like("authors_id", f"{SEED_PREFIX}%").execute()
    supabase.table("users").delete().like("users_id", f"{SEED_PREFIX}%").execute()
    supabase.table("stores").delete().like("stores_id", f"{SEED_PREFIX}%").execute()
    print("[OK] 기존 demo_core 행 정리")


def _delete_rows_for_user_rebuild(supabase, users_id: str) -> None:
    """FK 순서대로 해당 users_id 에 묶인 앱 행만 삭제 (books·stores·kg·authors 제외)."""
    uid = (users_id or "").strip()
    if not uid:
        return

    conv_res = supabase.table("conversation").select("conversation_id").eq("users_id", uid).execute()
    conv_ids = [r["conversation_id"] for r in (conv_res.data or []) if r.get("conversation_id")]
    for cid in conv_ids:
        supabase.table("conversation_messages").delete().eq("conversation_id", cid).execute()
    supabase.table("conversation").delete().eq("users_id", uid).execute()

    rev_res = supabase.table("reviews").select("reviews_id").eq("users_id", uid).execute()
    rev_ids = [r["reviews_id"] for r in (rev_res.data or []) if r.get("reviews_id")]
    for rid in rev_ids:
        supabase.table("comments").delete().eq("reviews_id", rid).execute()
        supabase.table("review_likes").delete().eq("reviews_id", rid).execute()
    supabase.table("review_likes").delete().eq("users_id", uid).execute()
    supabase.table("comments").delete().eq("users_id", uid).execute()
    supabase.table("reviews").delete().eq("users_id", uid).execute()

    coll_res = supabase.table("collections").select("collections_id").eq("users_id", uid).execute()
    cids = [r["collections_id"] for r in (coll_res.data or []) if r.get("collections_id")]
    for cid in cids:
        supabase.table("collection_books").delete().eq("collections_id", cid).execute()
    supabase.table("collections").delete().eq("users_id", uid).execute()

    sh_res = supabase.table("shelves").select("shelves_id").eq("users_id", uid).execute()
    sids = [r["shelves_id"] for r in (sh_res.data or []) if r.get("shelves_id")]
    for sid in sids:
        supabase.table("shelf_books").delete().eq("shelves_id", sid).execute()
    supabase.table("shelves").delete().eq("users_id", uid).execute()

    supabase.table("ratings").delete().eq("users_id", uid).execute()
    supabase.table("book_user_states").delete().eq("users_id", uid).execute()
    supabase.table("users").delete().eq("users_id", uid).execute()


def _resolve_user_ids(args: argparse.Namespace) -> tuple[list[str], bool]:
    """(user_ids, user_id_arg_ignored). --users>1 이면 demo_core_u_XX 다중 유저."""
    if args.users > 1:
        n = min(15, args.users)
        if (args.user_id or "").strip() not in ("", DEFAULT_DEV_USER_ID):
            print(
                f"[안내] --users={args.users} 이므로 --user-id 는 무시하고 "
                f"{SEED_PREFIX}_u_01 … 를 사용합니다.",
                file=sys.stderr,
            )
        return ([f"{SEED_PREFIX}_u_{i:02d}" for i in range(1, n + 1)], True)
    uid = (args.user_id or DEFAULT_DEV_USER_ID).strip()
    if not uid:
        print("[오류] --user-id 가 비었습니다.", file=sys.stderr)
        raise SystemExit(1)
    return ([uid], False)


def run(args: argparse.Namespace) -> None:
    _load_env()
    dry = args.dry_run
    user_ids, _ = _resolve_user_ids(args)
    n_users = len(user_ids)
    n_books = max(BOOK_SAMPLE_MIN, min(BOOK_SAMPLE_MAX, args.book_sample_size))

    supabase = None if dry else _create_client()

    if dry:
        print("[dry-run] 쓰기 없음")

    if args.replace and not dry:
        assert supabase is not None
        _delete_demo_rows(supabase, dry_run=False)
        for uid in user_ids:
            _delete_rows_for_user_rebuild(supabase, uid)
        print(f"[OK] 대상 사용자 {len(user_ids)}명 행 삭제(재시드 준비)")
    elif args.replace and dry:
        print("[dry-run] --replace 시 demo_core 및 대상 사용자 행 삭제 후 삽입 예정")

    if dry:
        book_rows = []
    else:
        assert supabase is not None
        if args.book_ids:
            ids = [x.strip() for x in args.book_ids if x and str(x).strip()]
            book_rows = []
            for i in range(0, len(ids), 50):
                chunk = ids[i : i + 50]
                res = (
                    supabase.table("books")
                    .select("id, authors, title, description, editorial_review, kdc_class_nm")
                    .in_("id", chunk)
                    .execute()
                )
                book_rows.extend(res.data or [])
        else:
            res = (
                supabase.table("books")
                .select("id, authors, title, description, editorial_review, kdc_class_nm")
                .order("id")
                .limit(n_books)
                .execute()
            )
            book_rows = list(res.data or [])

    if not dry and not book_rows:
        print("[오류] public.books 에서 가져온 도서가 없습니다. --book-id 를 지정하거나 카탈로그를 채우세요.", file=sys.stderr)
        raise SystemExit(1)

    if dry:
        print(f"예상: users_id={user_ids}, 샘플 책 ≤{n_books}권, authors 파생, …")
        return

    assert supabase is not None
    books_meta = {str(r["id"]): r for r in book_rows}
    book_ids = list(books_meta.keys())

    # --- users ---
    for i, uid in enumerate(user_ids, start=1):
        is_single_dev = n_users == 1 and uid == DEFAULT_DEV_USER_ID
        supabase.table("users").upsert(
            {
                "users_id": uid,
                "username": "dev_test_login_1" if is_single_dev else f"demo_login_{i:02d}",
                "password": "demo_not_for_prod",
                "nickname": "테스트독자1" if is_single_dev else f"데모독자{i:02d}",
                "profile_image_url": None,
                "bio": "로컬·하이브리드 추천 테스트용 계정" if is_single_dev else f"{SEED_PREFIX} 시드 계정",
                "preferred_genres": "소설,에세이",
            },
            on_conflict="users_id",
        ).execute()
    print(f"[OK] users {len(user_ids)} rows")

    # --- authors + book_authors (books.authors 파생) ---
    name_to_aid: dict[str, str] = {}
    for bid, row in books_meta.items():
        for name in parse_authors_field(str(row.get("authors") or "")):
            aid = author_id_from_name(name)
            if name not in name_to_aid:
                name_to_aid[name] = aid
                supabase.table("authors").upsert(
                    {"authors_id": aid, "name": name},
                    on_conflict="authors_id",
                ).execute()

    ba_count = 0
    for bid, row in books_meta.items():
        seen_pair: set[tuple[str, str]] = set()
        for name in parse_authors_field(str(row.get("authors") or "")):
            aid = author_id_from_name(name)
            key = (aid, bid)
            if key in seen_pair:
                continue
            seen_pair.add(key)
            supabase.table("book_authors").upsert(
                {"authors_id": aid, "books_id": bid, "role": "저자"},
                on_conflict="authors_id,books_id",
            ).execute()
            ba_count += 1
    print(f"[OK] authors {len(name_to_aid)}, book_authors {ba_count}")

    # --- stores (데모 고정) ---
    stores_data = [
        ("01", "교보문고 광화문점", "서울 종로구 종로 1", 37.5699, 126.9823),
        ("02", "영풍문고 코엑스점", "서울 강남구 영동대로 513", 37.5117, 127.0593),
        ("03", "알라딘 중고서점 강남점", "서울 강남구 테헤란로 415", 37.5012, 127.0365),
        ("04", "책읽는소리", "서울 마포구 와우산로 35", 37.5563, 126.9236),
        ("05", "그림책방", "서울 성동구 성수이로 7", 37.5446, 127.0559),
        ("06", "더 북 소사이어티", "서울 용산구 한강대로 366", 37.5297, 126.9658),
        ("07", "인문학 서가", "서울 종로구 인사동길 12", 37.5735, 126.9830),
        ("08", "책과 바다", "부산 해운대구 해운대해변로 264", 35.1587, 129.1604),
        ("09", "어린이 책놀이터", "대구 중구 동성로 2", 35.8714, 128.5948),
        ("10", "문학동네", "서울 마포구 상암산로 76", 37.5796, 126.8890),
        ("11", "반디앤루니스", "서울 송파구 올림픽로 240", 37.5125, 127.1028),
        ("12", "책발전소", "서울 은평구 진관2로 29", 37.6372, 126.9280),
        ("13", "이화여대 앞 서점", "서울 서대문구 이화여대길 52", 37.5598, 126.9467),
        ("14", "홍대 작은책방", "서울 마포구 와우산로 19", 37.5551, 126.9237),
        ("15", "강남 북카페", "서울 강남구 테헤란로 427", 37.5000, 127.0360),
    ]
    for sid, name, addr, lat, lng in stores_data:
        sk = f"{SEED_PREFIX}_store_{sid}"
        supabase.table("stores").upsert(
            {
                "stores_id": sk,
                "name": name,
                "address": addr,
                "latitude": lat,
                "longitude": lng,
                "phone": "02-0000-0000",
                "business_hours": "10:00–22:00",
            },
            on_conflict="stores_id",
        ).execute()
    print(f"[OK] stores {len(stores_data)} rows")

    # --- shelves (유저당 4종) ---
    shelf_key: dict[str, dict[str, str]] = {}
    for uid in user_ids:
        shelf_key[uid] = {}
        for st in SHELF_TYPES:
            slug = SHELF_SLUGS[st]
            sk = f"{uid}__{slug}"
            shelf_key[uid][st] = sk
            supabase.table("shelves").upsert(
                {"shelves_id": sk, "users_id": uid, "shelf_type": st},
                on_conflict="shelves_id",
            ).execute()
    print(f"[OK] shelves {len(user_ids) * len(SHELF_TYPES)} rows")

    # --- shelf_books: 대부분 읽은, 일부 읽는중/쇼핑 ---
    sb_count = 0
    nbook = len(book_ids)
    for idx, bid in enumerate(book_ids):
        uid = user_ids[idx % n_users]
        if nbook <= 2:
            sk = shelf_key[uid]["읽은"]
        elif idx >= nbook - 2:
            sk = shelf_key[uid]["쇼핑리스트" if idx == nbook - 1 else "읽는중"]
        else:
            sk = shelf_key[uid]["읽은"]
        supabase.table("shelf_books").upsert(
            {"books_id": bid, "shelves_id": sk},
            on_conflict="books_id,shelves_id",
        ).execute()
        sb_count += 1
    print(f"[OK] shelf_books {sb_count}")

    # --- ratings (읽은 책 위주) ---
    read_books: list[tuple[str, str]] = []
    for idx, bid in enumerate(book_ids):
        uid = user_ids[idx % n_users]
        if nbook <= 2:
            read_books.append((uid, bid))
        elif idx >= nbook - 2:
            continue
        else:
            read_books.append((uid, bid))
    for j, (uid, bid) in enumerate(read_books):
        score = round(3.5 + (j % 4) * 0.4, 1)
        if score > 5.0:
            score = 5.0
        supabase.table("ratings").upsert(
            {"users_id": uid, "books_id": bid, "score": score},
            on_conflict="users_id,books_id",
        ).execute()
    print(f"[OK] ratings {len(read_books)}")

    # --- book_user_states ---
    state_pairs: dict[tuple[str, str], str] = {}
    for uid, bid in read_books:
        state_pairs[(uid, bid)] = "REVIEW_POSTED"
    if nbook > 2:
        uid_r = user_ids[(nbook - 2) % n_users]
        bid_r = book_ids[nbook - 2]
        state_pairs[(uid_r, bid_r)] = "READING"
        uid_w = user_ids[(nbook - 1) % n_users]
        bid_w = book_ids[nbook - 1]
        state_pairs[(uid_w, bid_w)] = "LIST"
    for (uid, bid), st in state_pairs.items():
        supabase.table("book_user_states").upsert(
            {"users_id": uid, "books_id": bid, "shelf_state": st},
            on_conflict="users_id,books_id",
        ).execute()
    print("[OK] book_user_states")

    # --- reviews (단일 유저: 책 수에 맞춰 최대 BOOK_SAMPLE_MAX 권까지) ---
    n_rev = min(len(book_ids), BOOK_SAMPLE_MAX) if n_users == 1 else min(15, len(book_ids))
    review_ids: list[str] = []
    for i in range(n_rev):
        bid = book_ids[i]
        uid = user_ids[0] if n_users == 1 else user_ids[i % n_users]
        rid = f"{SEED_PREFIX}_rev_{i+1:02d}"
        review_ids.append(rid)
        meta = {k: str(books_meta[bid].get(k) or "") for k in ("title", "description", "editorial_review")}
        body = review_body_from_book(meta)
        supabase.table("reviews").upsert(
            {
                "reviews_id": rid,
                "users_id": uid,
                "books_id": bid,
                "content": body,
            },
            on_conflict="reviews_id",
        ).execute()
    print(f"[OK] reviews {n_rev}")

    # --- comments ---
    for i in range(n_rev):
        cid = f"{SEED_PREFIX}_cmt_{i+1:02d}"
        rid = review_ids[i]
        replier = user_ids[0] if n_users == 1 else user_ids[(i + 1) % n_users]
        supabase.table("comments").upsert(
            {
                "comments_id": cid,
                "reviews_id": rid,
                "users_id": replier,
                "content": "공감해요. 저도 비슷하게 느꼈습니다.",
            },
            on_conflict="comments_id",
        ).execute()
    print(f"[OK] comments {n_rev}")

    # --- review_likes ---
    for i in range(n_rev):
        uid = user_ids[0] if n_users == 1 else user_ids[(i + 2) % n_users]
        rid = review_ids[i]
        supabase.table("review_likes").upsert(
            {"users_id": uid, "reviews_id": rid},
            on_conflict="users_id,reviews_id",
        ).execute()
    print(f"[OK] review_likes {n_rev}")

    # --- collections (kdc 힌트) ---
    kdc_hints: dict[str, list[str]] = {}
    for bid in book_ids[:n_rev]:
        kdc = str(books_meta[bid].get("kdc_class_nm") or "").strip()
        top = kdc.split(">")[0].strip() if kdc else "이 책들"
        kdc_hints.setdefault(top, []).append(bid)

    n_coll = min(len(book_ids), BOOK_SAMPLE_MAX) if n_users == 1 else min(15, n_users)
    coll_ids: list[str] = []
    for i in range(n_coll):
        uid = user_ids[0] if n_users == 1 else user_ids[i]
        cid = f"{SEED_PREFIX}_col_{i+1:02d}"
        coll_ids.append(cid)
        title_hint = list(kdc_hints.keys())[i % len(kdc_hints)] if kdc_hints else "추천 모음"
        supabase.table("collections").upsert(
            {
                "collections_id": cid,
                "users_id": uid,
                "title": f"{title_hint}가 담긴 모음",
                "description": f"{SEED_PREFIX} 데모 컬렉션",
                "is_public": True,
            },
            on_conflict="collections_id",
        ).execute()
    print(f"[OK] collections {len(coll_ids)}")

    # --- collection_books ---
    cb_i = 0
    for i, cid in enumerate(coll_ids):
        if cb_i >= len(book_ids):
            break
        bid = book_ids[(i * 2) % len(book_ids)]
        supabase.table("collection_books").upsert(
            {
                "books_id": bid,
                "collections_id": cid,
                "order_index": 0,
            },
            on_conflict="books_id,collections_id",
        ).execute()
        cb_i += 1
        if i + 1 < len(book_ids):
            bid2 = book_ids[(i * 2 + 1) % len(book_ids)]
            if bid2 != bid:
                supabase.table("collection_books").upsert(
                    {
                        "books_id": bid2,
                        "collections_id": cid,
                        "order_index": 1,
                    },
                    on_conflict="books_id,collections_id",
                ).execute()
    print("[OK] collection_books")

    # --- conversation + messages ---
    n_conv = min(len(book_ids), BOOK_SAMPLE_MAX) if n_users == 1 else min(15, max(1, len(book_ids)))
    for i in range(n_conv):
        conv_id = f"{SEED_PREFIX}_conv_{i+1:02d}"
        uid = user_ids[0] if n_users == 1 else user_ids[i % n_users]
        is_book = i % 2 == 0
        bdetail = book_ids[i % len(book_ids)] if is_book else None
        ctype = "book_detail" if is_book else "agent"
        supabase.table("conversation").upsert(
            {
                "conversation_id": conv_id,
                "users_id": uid,
                "books_id": bdetail,
                "type": ctype,
            },
            on_conflict="conversation_id",
        ).execute()
        title = str(books_meta[bdetail].get("title") or "") if bdetail else ""
        auth = str(books_meta[bdetail].get("authors") or "") if bdetail else ""
        if ctype == "book_detail":
            msgs = [
                ("user", f"《{title}》에 대해 짧게 설명해줘 (저자: {auth})"),
                ("ai", f"'{title}'는 독자의 질문에 맞춰 핵심만 정리해 드릴게요."),
                ("user", "고마워!"),
            ]
        else:
            msgs = [
                ("user", "오늘 읽을 책 추천해줘"),
                ("ai", "선호 장르를 알려주시면 맞춤으로 골라볼게요."),
            ]
        for j, (role, content) in enumerate(msgs):
            mid = f"{conv_id}_m{j+1}"
            supabase.table("conversation_messages").upsert(
                {
                    "conversation_messages_id": mid,
                    "conversation_id": conv_id,
                    "role": role,
                    "content": content[:8000],
                    "intent": "smalltalk" if ctype == "agent" else "book_qna",
                },
                on_conflict="conversation_messages_id",
            ).execute()
    print("[OK] conversation + conversation_messages")

    print()
    ex_uid = user_ids[0]
    print(f"완료. 예: GET /api/books/<id>/comments , /api/users/{ex_uid}/collections")


def main() -> None:
    p = argparse.ArgumentParser(description="Supabase 코어 데모 시드 (bookjuk_full_schema DDL)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--replace",
        action="store_true",
        help="demo_core_* 및 대상 users_id 행 삭제 후 재삽입",
    )
    p.add_argument(
        "--user-id",
        type=str,
        default=DEFAULT_DEV_USER_ID,
        help=f"단일 유저 모드(--users 1)일 때 users_id (기본 {DEFAULT_DEV_USER_ID})",
    )
    p.add_argument(
        "--users",
        type=int,
        default=1,
        help="데모 사용자 수. 1이면 --user-id 한 명만. 2 이상이면 demo_core_u_01… (최대 15)",
    )
    p.add_argument(
        "--book-sample-size",
        type=int,
        default=BOOK_SAMPLE_DEFAULT,
        help=f"--book-ids 없을 때 books 에서 가져올 권수 ({BOOK_SAMPLE_MIN}~{BOOK_SAMPLE_MAX}로 클램프)",
    )
    p.add_argument("--book-ids", nargs="+", metavar="ID", help="도서 id(books.id) 목록; 없으면 order by id 로 샘플")
    args = p.parse_args()
    if args.users < 1:
        print("[오류] --users 는 1 이상이어야 합니다.", file=sys.stderr)
        raise SystemExit(1)
    if args.users > 15:
        print("[오류] --users 는 최대 15 입니다.", file=sys.stderr)
        raise SystemExit(1)
    run(args)


if __name__ == "__main__":
    main()
