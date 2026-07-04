"""NetworkX KG ↔ Supabase (`kg_nodes`, `kg_edges`) 전체 스냅샷 저장/로드.

`HYBRID_PERSIST_KG=1` 이고 서비스 롤 클라이언트가 있으면 파이프라인이 자동 호출한다.
"""
from __future__ import annotations

import math
from typing import Any

import networkx as nx

from .phase1_kg.kg_store import NetworkXKGStore

_BATCH = 400


def _json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, float):
        return obj
    try:
        import numpy as np

        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except Exception:
        pass
    return str(obj)


def save_kg_to_supabase(supabase: Any, store: NetworkXKGStore) -> None:
    """KG 전체를 삭제 후 재삽입한다. `clear_hybrid_kg` RPC 필요."""
    if supabase is None:
        return

    G = store.graph
    node_rows: list[dict[str, Any]] = []
    for nid, data in G.nodes(data=True):
        node_rows.append({
            "kg_nodes_id": str(nid),
            "attrs": _json_safe(dict(data)),
        })

    edge_rows: list[dict[str, Any]] = []
    for u, v, k, data in G.edges(keys=True, data=True):
        d = dict(data)
        rel = str(d.pop("relation", "RELATED_TO"))
        conf = float(d.pop("confidence", 1.0))
        edge_rows.append({
            "src_id": str(u),
            "dst_id": str(v),
            "edge_key": int(k),
            "relation": rel,
            "confidence": conf,
            "attrs": _json_safe(d),
        })

    try:
        supabase.rpc("clear_hybrid_kg").execute()
    except Exception as e:
        print(f"[WARN] clear_hybrid_kg 실패 (마이그레이션 적용 여부 확인): {e}")
        return

    for i in range(0, len(node_rows), _BATCH):
        chunk = node_rows[i : i + _BATCH]
        supabase.table("kg_nodes").insert(chunk).execute()

    for i in range(0, len(edge_rows), _BATCH):
        chunk = edge_rows[i : i + _BATCH]
        supabase.table("kg_edges").insert(chunk).execute()

    print(f"[KG] Supabase 저장 완료: 노드 {len(node_rows)}개, 엣지 {len(edge_rows)}개")


def load_kg_from_supabase(supabase: Any) -> NetworkXKGStore | None:
    """저장된 KG가 있으면 NetworkXKGStore로 복원한다."""
    if supabase is None:
        return None

    try:
        nres = supabase.table("kg_nodes").select("kg_nodes_id, attrs").execute()
        eres = supabase.table("kg_edges").select(
            "src_id, dst_id, edge_key, relation, confidence, attrs"
        ).execute()
    except Exception as e:
        print(f"[WARN] KG Supabase 조회 실패: {e}")
        return None

    nodes = getattr(nres, "data", None) or []
    edges = getattr(eres, "data", None) or []
    if not nodes and not edges:
        return None

    store = NetworkXKGStore()
    store.graph = nx.MultiDiGraph()
    store._entity_ids = []
    store._relations = set()

    for row in nodes:
        nid = str(row.get("kg_nodes_id") or "").strip()
        if not nid:
            continue
        raw = row.get("attrs")
        if not isinstance(raw, dict):
            raw = {}
        node_type = str(raw.get("type", "Unknown"))
        rest = {k: v for k, v in raw.items() if k != "type"}
        store.add_node(nid, node_type, **rest)

    for row in edges:
        u = str(row.get("src_id") or "").strip()
        v = str(row.get("dst_id") or "").strip()
        if not u or not v:
            continue
        k = int(row.get("edge_key") or 0)
        rel = str(row.get("relation") or "RELATED_TO")
        conf = float(row.get("confidence") or 1.0)
        raw = row.get("attrs")
        extra = dict(raw) if isinstance(raw, dict) else {}
        if u not in store.graph:
            store.add_node(u, "Unknown", label=u)
        if v not in store.graph:
            store.add_node(v, "Unknown", label=v)
        store.graph.add_edge(u, v, key=k, relation=rel, confidence=conf, **extra)

    store._entity_ids = list(store.graph.nodes())
    store._relations = set()
    for _, _, _, d in store.graph.edges(keys=True, data=True):
        r = d.get("relation") or "RELATED_TO"
        store._relations.add(str(r))
    return store
