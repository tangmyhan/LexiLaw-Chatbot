# -*- coding: utf-8 -*-
import os, asyncio
from typing import List, Dict
from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from FlagEmbedding import FlagReranker
from dotenv import load_dotenv


load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL") 
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")  

COLLECTION = "legal_laws"
EMB_MODEL = "BAAI/bge-m3"                         # dense (đã dùng khi indexing)
RERANKER = "BAAI/bge-reranker-v2-m3"  # cross-encoder đa ngôn ngữ

TOPK_RETRIEVE = 15
TOPK_FINAL = 5

async def dense_search(client: AsyncQdrantClient, query_vec, filters: Dict=None):
    return await client.search(
        collection_name=COLLECTION,
        query_vector=("dense", query_vec),
        limit=TOPK_RETRIEVE,
        with_payload=True,
        query_filter=Filter(
            must=[
                FieldCondition(key="metadata.doc_info.doc_number", match=MatchValue(value=filters["doc_number"]))
            ]
        ) if filters and "doc_number" in filters else None
    )

def format_citation(payload):
    h = payload["metadata"]["hierarchy"]
    dn = payload["metadata"]["doc_info"]["doc_number"]
    cite = f'{dn} - Điều {h["article_no"]}'
    if h.get("clause_no"): cite += f' Khoản {h["clause_no"]}'
    if h.get("point"): cite += f' Điểm {h["point"]}'
    return cite

async def main():
    # 1) models
    emb = SentenceTransformer(EMB_MODEL)
    # reranker = CrossEncoder(RERANKER)
    reranker = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=True) # Setting use_fp16 to True speeds up computation with a slight performance degradation

    # 2) query
    user_query = "Nghỉ việc hợp đồng xác định thời hạn thì phải báo trước bao nhiêu ngày?"
    qv = emb.encode([user_query], normalize_embeddings=True)[0].tolist()

    # 3) search dense
    async with AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY) as client:
        dense_hits = await dense_search(client, qv, filters=None)

    # 4) rerank cross-encoder (query, doc)
    pairs = [(user_query, hit.payload["content"]) for hit in dense_hits]
    scores = reranker.rerank_pairs(pairs)  # danh sách float
    reranked = sorted(zip(dense_hits, scores), key=lambda x: x[1], reverse=True)[:TOPK_FINAL]

    # 5) in ra kết quả (có thể feed vào LLM)
    for i, (hit, s) in enumerate(reranked, 1):
        print(f"[{i}] {format_citation(hit.payload)}  |  score={s:.4f}")
        print(hit.payload["content"][:300].replace("\n"," ") + " ...\n")

if __name__ == "__main__":
    asyncio.run(main())