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

reranker_service = RerankerService()