import asyncio
from functools import partial
from sentence_transformers import SentenceTransformer
from app.core.config import settings

class EmbeddingService:
    def __init__(self):
        # Load model 1 lần duy nhất
        self.model = SentenceTransformer("BAAI/bge-m3")

    async def encode_query(self, query_text: str):
        """Mã hóa câu hỏi sang dense vector (Async)"""
        loop = asyncio.get_running_loop()
        # Chạy trong threadpool để không block FastAPI
        func = partial(self.model.encode, query_text, normalize_embeddings=True)
        vector = await loop.run_in_executor(None, func)
        return vector.tolist()

embedding_service = EmbeddingService()