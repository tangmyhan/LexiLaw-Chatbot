import asyncio
from functools import partial
from FlagEmbedding import FlagReranker
from typing import List, Any

class RerankerService:
    def __init__(self):
        self.reranker = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=True)

    async def rerank(self, query: str, hits: List[Any], top_k: int = 5):
        if not hits: return []

        # (query, content)
        pairs = [(query, h.payload["content"]) for h in hits]
        
        loop = asyncio.get_running_loop()
        # Chấm điểm đồng bộ trong threadpool
        func = partial(self.reranker.compute_score, pairs)
        scores = await loop.run_in_executor(None, func)
        
        # Sắp xếp lại dựa trên score của reranker
        scored_hits = sorted(zip(hits, scores), key=lambda x: x[1], reverse=True)
        
        # top_k kết quả tốt nhất
        return [hit for hit, score in scored_hits[:top_k]]


import cohere
from app.core.config import settings

class CohereReranker:
    def __init__(self):
        self.co = cohere.Client(settings.COHERE_API_KEY)

    async def rerank(self, query, initial_hits, top_k=5):
        if not initial_hits: return []
        
        # Chuẩn bị dữ liệu cho Cohere
        docs = [h.payload['content'] for h in initial_hits]
        
        # Gọi API (Rerank v3.5 hỗ trợ tiếng Việt)
        response = self.co.rerank(
            model='rerank-v3.5',
            query=query,
            documents=docs,
            top_n=top_k
        )
        
        # Áp dụng lại thứ tự mới vào initial_hits gốc
        final_results = []
        for res in response.results:
            hit = initial_hits[res.index]
            hit.score = res.relevance_score # Cập nhật điểm số mới
            final_results.append(hit)
            
        return final_results

# reranker_service = RerankerService()
reranker_service = CohereReranker()