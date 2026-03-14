import os
import asyncio
from typing import List, Dict
import uuid
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Prefetch,
    FusionQuery,
    Fusion,
)

from sentence_transformers import SentenceTransformer

from dotenv import load_dotenv
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")  

NAMESPACE_LAW = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

COLLECTION = "legal_laws"


class HybridLegalRetriever:

    def __init__(self):

        self.model = SentenceTransformer("BAAI/bge-m3")

        self.client = AsyncQdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            timeout=60.0
        )

    async def embed_query(self, query: str):

        embeddings = self.model.encode(
            [query],
            normalize_embeddings=True,
            return_sparse=True
        )

        dense_vector = embeddings["dense"][0]

        sparse = embeddings["sparse"][0]

        sparse_vector = {
            "indices": sparse.indices.tolist(),
            "values": sparse.values.tolist()
        }

        return dense_vector, sparse_vector

    async def search(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict]:

        dense_vector, sparse_vector = await self.embed_query(query)

        results = await self.client.query_points(
            collection_name=COLLECTION,

            prefetch=[

                Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=20
                ),

                Prefetch(
                    query=sparse_vector,
                    using="text-sparse",
                    limit=20
                ),
            ],

            query=FusionQuery(fusion=Fusion.RRF),

            limit=top_k
        )

        return results.points

    def format_results(self, points):

        results = []

        for p in points:

            payload = p.payload
            meta = payload["metadata"]

            results.append({
                "score": p.score,
                "content": payload["content"],
                "law": meta["doc_info"]["title"],
                "article": meta["hierarchy"]["article_no"],
                "chapter": meta["hierarchy"]["chapter"],
            })

        return results


async def main():

    retriever = HybridLegalRetriever()

    query = "người lao động được nghỉ phép năm bao nhiêu ngày"

    points = await retriever.search(query)

    results = retriever.format_results(points)

    for r in results:

        print("Score:", r["score"])
        print("Law:", r["law"])
        print("Article:", r["article"])
        print("Content:", r["content"])
        print("-" * 80)


if __name__ == "__main__":
    asyncio.run(main())