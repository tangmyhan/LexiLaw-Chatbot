from typing import List, Dict, Any
from app.agents.tools import legal_tools
from app.services.qdrant_service import qdrant_legal_service
from app.services.reranker import reranker_service
from app.services.memory import memory_service

class ResearcherAgent:

    async def gather_all_evidence(self, query: str) -> List[Dict[str, Any]]:
        """
        1) Check cache trước
        2) Nếu không có, Qdrant semantic seeds + rerank
        3) Graph expand (owner spans + references + semantics + mention spans)
        4) Fusion scoring rồi hợp nhất thành list context (để cho Answer Agent)
        5) Lưu cache
        """
        cached = await memory_service.get_cached_result(query)
        if cached:
            return cached

        # Qdrant + rerank
        raw_hits = await qdrant_legal_service.hybrid_search(query, top_k=10)
        if not raw_hits: 
            return []
        hits = await reranker_service.rerank(query, raw_hits, top_k=5)

        # Graph expand dựa trên article_ids từ hits
        graph_ctx = await legal_tools.search_graph_references(raw_hits, limit_spans=40)

        # Fusion: cho điểm graph-items
        def gscore(edge_type: str) -> float:
            return {
                "REFERENCES": 1.3, "PENALIZES": 1.3, "HAS_PENALTY": 1.25,
                "REGULATES": 1.2, "PROHIBITS": 1.2, "ALLOWS": 1.15,
                "DEFINES": 1.1, "INVOLVES": 1.0, "MENTIONS": 1.0, "BELONGS_TO": 1.0
            }.get(edge_type, 1.0)

        base = []
        for h in hits:
            m = h.payload['metadata']
            base.append({
                "source": f"{m['doc_info']['title']} - Điều {m['hierarchy']['article_no']}",
                "content": h.payload['content'],
                "score": 0.6 * float(h.score),  # α * semantic
                "citation": {
                    "doc_number": m['doc_info'].get('doc_number'),
                    "article_no": m['hierarchy'].get('article_no'),
                    "clause_no": m['hierarchy'].get('clause_no'),
                    "point": m['hierarchy'].get('point')
                }
            })

        # Owner spans (BELONGS_TO) – score thấp hơn seeds 1 chút nếu duplicate
        for s in graph_ctx["owner_spans"]:
            base.append({
                "source": s.get("article_id"),
                "content": s.get("content"),
                "score": 0.4 * gscore("BELONGS_TO"),
                "graph_tag": "owner_span"
            })

        # Mention spans (Span -> MENTIONS -> Event/Actor)
        for s in graph_ctx["mention_spans"]:
            ms = s.get("mentions", [])
            tag = ", ".join({ (m.get("type") or "")+":"+(m.get("name") or "") for m in ms })
            base.append({
                "source": s.get("article_id"),
                "content": s.get("content"),
                "score": 0.45 * gscore("MENTIONS"),
                "graph_tag": f"mentions({tag})"
            })

        # References (Article -> Article)
        for r in graph_ctx["references"]:
            base.append({
                "source": f"{r['src']} → {r['dst']}",
                "content": f"Tham chiếu tới {r['dst']} (doc={r['dst_doc_key']})",
                "score": 0.5 * gscore("REFERENCES"),
                "graph_tag": "ref"
            })

        # Semantics (LegalConcept/Event/Actor/Penalty) -> chèn summary ngắn làm context hook
        for e in graph_ctx["semantics"]["events"]:
            base.append({
                "source": e.get("article_id"),
                "content": f"Sự kiện/hành vi: {e.get('name')}",
                "score": 0.5 * gscore("REGULATES"),
                "graph_tag": "event"
            })
        for p in graph_ctx["semantics"]["penalties"]:
            base.append({
                "source": p.get("article_id"),
                "content": f"Chế tài: {p.get('name')} (min={p.get('amount_min')} max={p.get('amount_max')} {p.get('unit')})",
                "score": 0.55 * gscore("PENALIZES"),
                "graph_tag": "penalty"
            })
        for c in graph_ctx["semantics"]["concepts"]:
            base.append({
                "source": c.get("article_id"),
                "content": f"Khái niệm: {c.get('name')}",
                "score": 0.4 * gscore("DEFINES"),
                "graph_tag": "concept"
            })

        # Sort by score desc & remove empties
        base = [b for b in base if b.get("content")]
        base.sort(key=lambda x: x["score"], reverse=True)
        # Dedup by content
        seen = set(); out=[]
        for b in base:
            key = b["content"].strip()
            if key not in seen:
                seen.add(key); out.append(b)

        # Giới hạn context để giữ token budget
        result = out[:40]

        # 5) Lưu cache
        await memory_service.set_cached_result(query, result)

        return result
