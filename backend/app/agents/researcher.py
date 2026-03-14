from app.agents.tools import legal_tools

class ResearcherAgent:
    async def gather_all_evidence(self, query: str):
        # Chạy song song Qdrant và Neo4j (nếu có) để tối ưu tốc độ
        vector_data = await legal_tools.search_knowledge_base(query)
        # graph_data = await legal_tools.search_graph_references(query)
        
        return vector_data # Trả về context để Answer Agent sử dụng