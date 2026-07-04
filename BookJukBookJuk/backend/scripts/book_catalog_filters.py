"""booksCatalog / DB 행에서 어린이·교육용 도서를 걸러내기 위한 공통 규칙.

KDC 경로·표제·출판사 등을 조합한다. (완벽한 분류가 아니라 카탈로그 시드용 휴리스틱)

시리즈: **표제(title) 문자열만**으로 판단한다. (부분 일치 키워드·만화로 보는·고믹·Why·권차·표제 내 총 N권 등.
본문/알라딘 메타 반복·seriesInfo·학습만화 분류는 사용하지 않음 — 중복·오탐 줄이기 위함.)

**전체 목록 기준 군집:** 두 표제의 최장 공통 부분수열(LCS) 길이를 짧은 쪽 제목 길이로 나눈 값이 50% 이상이면 “유사”로 간선을 두고,
유사 관계로 연결된 책이 3권 이상이면(연결 요소 크기 ≥3) 해당 책들은 시리즈로 보고 제외한다. (단행본 위주 유지용)
"""
from __future__ import annotations

import re
from collections import defaultdict


def _norm(s: str) -> str:
    return (s or "").strip()


def is_education_book(kdc_nm: str, title: str, description: str) -> bool:
    """교육학 분류, 학습·교과·시험 위주 도서."""
    k = _norm(kdc_nm)
    parts = [p.strip() for p in k.split(">") if p.strip()]
    if "교육학" in parts:
        return True
    t = _norm(title)
    d = _norm(description)
    blob = f"{t} {d}"
    edu_title = (
        "학습만화",
        "교과서",
        "참고서",
        "문제집",
        "수능",
        "수험",
        "EBS",
        "초등과학",
        "초등국어",
        "개념잡기",
        "실력완성",
        "평가문제",
        "전국연합",
    )
    if any(x in blob for x in edu_title):
        return True
    if re.search(r"\bWhy\?\s*초등", blob):
        return True
    return False


def is_children_book(kdc_nm: str, title: str, publisher: str, description: str) -> bool:
    """어린이·유아·그림책·아동 대상 위주."""
    k = _norm(kdc_nm)
    t = _norm(title)
    p = _norm(publisher)
    d = _norm(description)

    child_in_kdc = (
        "아동문학",
        "어린이",
        "유아",
        "초등교육",
        "청소년문학",
        "그림책",
    )
    for phrase in child_in_kdc:
        if phrase in k:
            return True

    blob = f"{t} {d} {p}"
    child_blob = (
        "그림책",
        "유아",
        "어린이",
        "초등학교",
        "주니어",
        "토토북",
        "어린이과학동아",
        "인문학동화",
        "아기 ",
    )
    if any(x in blob for x in child_blob):
        return True
    if "주니어" in p or "(주니어)" in t:
        return True
    return False


def explain_skip_content_filter(row: dict) -> str | None:
    """통과면 None, 건너뛸 때 사람이 읽을 수 있는 이유 한 줄."""
    kdc_nm = str(row.get("kdc_class_nm") or "")
    title = str(row.get("title") or "")
    publisher = str(row.get("publisher") or "")
    description = str(row.get("description") or "")

    if is_education_book(kdc_nm, title, description):
        return "교육/학습/시험류 필터"
    if is_children_book(kdc_nm, title, publisher, description):
        return "어린이·유아·아동문학류 필터"
    return None


def should_keep_book(row: dict) -> bool:
    """어린이·교육용이 아니면 True."""
    return explain_skip_content_filter(row) is None


# 시리즈 표제: 부분 일치 (긴 문자열을 앞에 두면 같은 표제에서 먼저 매칭)
# — 알라딘/도서관 표기 차이(띄어쓰기)로 같은 시리즈가 다른 문자열로 올 수 있어 변형을 둔다.
_KNOWN_SERIES_TITLE_SUBSTRINGS = (
    "그리스 로마 신화",
    "그리스 로마신화",
    "설민석의",
    "놓지마 과학",
    "내일은 실험왕",
    "내일은 발명왕",
    "도전 요리왕",
    "한자귀신",
    "전천당",
    "영단어 원정대",
    "그램그램",
    "마법천자문",
    "책이나",
    "쿠키런",
    "메이플스토리",
    "메이플 스토리",
    "엉덩이 탐정",
    "엉덩이탐정",
    "흔한남매",
    "파워 바이블",
    "파워바이블",
)


def _series_rules_from_title_only(title: str) -> str | None:
    """표제만 보고 시리즈로 볼 때 이유. 통과면 None."""
    t = _norm(title)
    if not t:
        return None

    for needle in _KNOWN_SERIES_TITLE_SUBSTRINGS:
        if needle in t:
            return f"시리즈 표제 키워드: {needle}"

    if re.search(r"만화\s*로\s*보는", t):
        return "시리즈 표제: 만화로 보는 …"

    if t.startswith("고믹 ") or re.search(r"^고믹\s", t) or re.search(r"[\s·【\[\(]고믹\s", t):
        return "시리즈 표제: 고믹 …"

    if re.search(r"Why", t, re.I):
        return "시리즈 표제: Why"

    return None


def _title_has_series_volume_marker(title: str) -> bool:
    """표제에 권차·세트 등 시리즈 흔적이 있으면 True."""
    t = _norm(title)
    if not t:
        return False
    patterns = (
        re.compile(r"제\s*\d{1,4}\s*권"),
        re.compile(r"\d{1,4}\s*권\s*중"),
        re.compile(r"\d{1,4}\s*권\s*세트"),
        re.compile(r"[\[【〈]\s*\d{1,4}\s*권\s*[\]】〉]"),
    )
    return any(p.search(t) for p in patterns)


def estimate_series_total_volumes_from_title(title: str) -> int | None:
    """표제에서만 시리즈 총 권수 후보를 추정. 없거나 불명확하면 None."""
    blob = _norm(title)
    if not blob:
        return None

    candidates: list[int] = []

    for rx in (
        re.compile(r"총\s*(\d{1,4})\s*권"),
        re.compile(r"전\s*(\d{1,4})\s*권"),
        re.compile(r"시리즈\s*\(?\s*(\d{1,4})\s*권\s*\)?"),
        re.compile(r"\(\s*(\d{1,4})\s*권\s*중"),
        re.compile(r"(\d{1,4})\s*권\s*중\s*제?\d{1,4}\s*권"),
    ):
        for m in rx.finditer(blob):
            try:
                n = int(m.group(1))
            except (ValueError, IndexError):
                continue
            if 1 <= n <= 2000:
                candidates.append(n)

    if not candidates:
        return None
    return max(candidates)


def estimate_series_total_volumes(aladin: dict, title: str, description: str = "") -> int | None:
    """호환용 — 표제만 사용 (aladin·description 무시)."""
    return estimate_series_total_volumes_from_title(title)


def explain_skip_series(
    aladin: dict,
    row: dict,
    *,
    max_volumes_keep: int = 1,
) -> str | None:
    """시리즈 규칙으로 제외할 때 이유. 통과면 None. **표제(title)만** 사용한다.

    max_volumes_keep: 표제에서 추정한 총 권수가 이 값 *초과*이면 제외 (기본 1 → 2권 이상).
    aladin 인자는 호환을 위해 받지만 시리즈 판별에 쓰지 않는다.
    """
    _ = aladin
    title = _norm(str(row.get("title") or ""))

    hit = _series_rules_from_title_only(title)
    if hit:
        return hit

    if _title_has_series_volume_marker(title):
        return "표제에 시리즈 권차/세트 표기"

    est = estimate_series_total_volumes_from_title(title)
    if est is not None and est > max_volumes_keep:
        return f"표제에서 시리즈 총 권수 추정 {est}권 (>{max_volumes_keep}권)"
    return None


def should_keep_compact_series(
    aladin: dict,
    row: dict,
    *,
    max_volumes_keep: int = 1,
) -> bool:
    """시리즈 규칙에 걸리면 False (단행본 위주 유지).

    max_volumes_keep=1 → 추정 총 2권 이상이면 제외. 권수 미상·단일이면 True.
    """
    return explain_skip_series(aladin, row, max_volumes_keep=max_volumes_keep) is None


def _lcs_length(a: str, b: str) -> int:
    """최장 공통 부분수열 길이 (O(m·n) 공간, 표제 길이가 짧다는 전제)."""
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        ca = a[i - 1]
        for j in range(1, n + 1):
            if ca == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev = curr
    return prev[n]


class _UnionFind:
    __slots__ = ("p", "sz")

    def __init__(self, n: int) -> None:
        self.p = list(range(n))
        self.sz = [1] * n

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.sz[ra] < self.sz[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        self.sz[ra] += self.sz[rb]


def map_ids_to_similar_title_cluster_skip(
    rows: list[dict],
    *,
    min_lcs_ratio: float = 0.5,
    min_cluster_size: int = 3,
    id_key: str = "id",
    title_key: str = "title",
) -> dict[str, str]:
    """DB·목록 전체를 봤을 때, 표제만으로 시리즈 군집을 찾아 삭제 사유를 붙인다.

    - 두 행의 표제에 대해 (LCS 길이) / (둘 중 짧은 표제 길이) >= min_lcs_ratio 이면 같은 그룹으로 연결(Union-Find).
    - 연결 요소의 크기가 min_cluster_size 이상이면, 그 안의 모든 id에 동일한 skip 이유를 매긴다.

    per-row `explain_skip_series`와 별개: **전역**으로만 판별 가능하다.
    """
    if min_cluster_size < 2:
        min_cluster_size = 2

    items: list[tuple[str, str]] = []
    for r in rows:
        bid = str(r.get(id_key) or "").strip()
        title = _norm(str(r.get(title_key) or ""))
        if bid and title:
            items.append((bid, title))

    n = len(items)
    if n < min_cluster_size:
        return {}

    # 정수 임계: ratio >= 0.5  ⟺  2*LCS >= shorter_len
    uf = _UnionFind(n)
    titles = [t for _, t in items]

    for i in range(n):
        ti = titles[i]
        for j in range(i + 1, n):
            tj = titles[j]
            shorter = min(len(ti), len(tj))
            if shorter == 0:
                continue
            # 빠른 동치: ti == tj
            if ti == tj:
                uf.union(i, j)
                continue
            lcs = _lcs_length(ti, tj)
            if min_lcs_ratio == 0.5:
                if 2 * lcs < shorter:
                    continue
            elif lcs < min_lcs_ratio * shorter - 1e-12:
                continue
            uf.union(i, j)

    by_root: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        by_root[uf.find(i)].append(i)

    pct = int(round(min_lcs_ratio * 100))
    reason = f"시리즈: 표제 유사군 (LCS/짧은쪽≥{pct}%, {min_cluster_size}권 이상)"
    out: dict[str, str] = {}
    for members in by_root.values():
        if len(members) < min_cluster_size:
            continue
        for idx in members:
            out[items[idx][0]] = reason
    return out


def pick_per_sector(rows: list[dict], per_sector: int = 50) -> list[dict]:
    """sector(0~9)별로 최대 per_sector권, id 기준 정렬."""
    by_sector: dict[int, list[dict]] = {i: [] for i in range(10)}
    for r in rows:
        try:
            s = int(r.get("sector") or 0)
        except (TypeError, ValueError):
            s = 0
        if 0 <= s <= 9:
            by_sector[s].append(r)

    out: list[dict] = []
    for s in range(10):
        chunk = sorted(by_sector[s], key=lambda x: str(x.get("id") or ""))
        out.extend(chunk[:per_sector])
    return out
