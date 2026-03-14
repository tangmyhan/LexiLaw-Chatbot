from app.services.qdrant_service import qdrant_legal_service
from app.services.reranker import reranker_service
# from app.services.neo4j import neo4j_service # Mở khi bạn đã build Graph

class LegalTools:
    async def search_knowledge_base(self, query: str):
        """Kết hợp Hybrid Search Qdrant và Re-ranking"""
        # 1. Tìm kiếm Hybrid (RRF) - lấy 15 kết quả
        initial_hits = await qdrant_legal_service.hybrid_search(query, top_k=15)
        
        # 2. Re-ranking - lấy 5 kết quả tốt nhất
        final_hits = await reranker_service.rerank(query, initial_hits, top_k=5)
        
        # 3. Format kết quả cho LLM dễ đọc
        formatted = []
        for h in final_hits:
            m = h.payload['metadata']
            formatted.append({
                "source": f"{m['doc_info']['title']} - Điều {m['hierarchy']['article_no']}",
                "content": h.payload['content']
            })
        return formatted

    async def search_graph_references(self, query: str):
        """Dành cho GraphRAG - Tìm quan hệ dẫn chiếu (Neo4j)"""
        # Logic gọi neo4j_service sẽ nằm ở đây
        return []

legal_tools = LegalTools()