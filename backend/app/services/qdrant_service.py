from qdrant_client import models
from app.core.qdrant import qdrant_client
from app.core.config import settings
from app.services.embedding import embedding_service

class QdrantLegalService:
    async def hybrid_search(self, query_text: str, top_k: int = 15):
        # Lấy Dense Vector
        dense_vector = await embedding_service.encode_query(query_text)

        # Hybrid Query (RRF)
        res = await qdrant_client.query_points(
            collection_name=settings.COLLECTION_NAME,
            prefetch=[
                # Sparse (BM25 Qdrant-side)
                models.Prefetch(
                    query=models.Document(text=query_text, model="Qdrant/bm25"),
                    using="text-sparse",
                    limit=max(top_k * 3, 20),
                ),
                # Dense
                models.Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=max(top_k * 3, 20),
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        
        # points
        return getattr(res, "points", None) or getattr(res, "result", None) or []

qdrant_legal_service = QdrantLegalService()