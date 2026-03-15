from app.services.qdrant_service import qdrant_legal_service
from app.services.reranker import reranker_service
from app.services.neo4j_service import neo4j_service
from typing import List, Dict, Any

class LegalTools:
    async def search_knowledge_base(self, query: str):
        """Kết hợp Hybrid Search Qdrant và Re-ranking"""
        # 1. Tìm kiếm Hybrid (RRF) - lấy 5 kết quả
        initial_hits = await qdrant_legal_service.hybrid_search(query, top_k=5)
        
        # 2. Re-ranking - lấy 3 kết quả tốt nhất
        final_hits = await reranker_service.rerank(query, initial_hits, top_k=3)
        
        # 3. Format kết quả cho LLM dễ đọc
        formatted = []
        for h in final_hits:
            m = h.payload['metadata']
            formatted.append({
                "source": f"{m['doc_info']['title']} - Điều {m['hierarchy']['article_no']}",
                "content": h.payload['content']
            })
        return formatted

    async def search_graph_references(self, qdrant_hits: List[Any], limit_spans: int = 30) -> Dict[str, Any]:
        """
        Input: raw Qdrant hits => derive article_ids => expand graph context
        Returns a dict that includes owner_spans, references, semantic nodes, mention_spans
        """
        article_ids = await neo4j_service.article_ids_from_qdrant_hits(qdrant_hits)
        if not article_ids:
            return {"owner_spans": [], "references": [], "semantics":{"concepts":[],"events":[],"actors":[],"penalties":[]}, "mention_spans":[]}
        return await neo4j_service.expand_from_articles(article_ids, limit_spans=limit_spans)

legal_tools = LegalTools()