from app.services.qdrant_service import qdrant_legal_service
from app.services.reranker import reranker_service
from app.services.neo4j_service import neo4j_service
from typing import List, Dict, Any

class LegalTools:
    async def search_knowledge_base(self, query: str):
        """Kết hợp Hybrid Search Qdrant và Re-ranking"""
        # tìm kiếm Hybrid (RRF)
        initial_hits = await qdrant_legal_service.hybrid_search(query, top_k=10)
        
        # Re-ranking
        final_hits = await reranker_service.rerank(query, initial_hits, top_k=5)
        
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

    async def get_graph_visualization(self, query: str) -> Dict[str, Any]:
        """
        Lấy dữ liệu visualization graph cho query
        """
        # Tìm kiếm Qdrant để lấy article_ids
        initial_hits = await qdrant_legal_service.hybrid_search(query, top_k=10)
        article_ids = await neo4j_service.article_ids_from_qdrant_hits(initial_hits)
        return await neo4j_service.get_graph_visualization_data(article_ids)

legal_tools = LegalTools()