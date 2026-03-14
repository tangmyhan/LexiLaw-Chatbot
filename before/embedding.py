# # -*- coding: utf-8 -*-
# import json
# import uuid
# import asyncio
# import os
# from functools import partial
# from typing import List, Dict

# from qdrant_client import AsyncQdrantClient
# from qdrant_client.models import VectorParams, Distance, PointStruct
# from sentence_transformers import SentenceTransformer

# # --- Cấu hình ---
# QDRANT_URL = os.getenv("QDRANT_URL") 
# QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
# HF_TOKEN = os.getenv("HF_TOKEN")  # tùy chọn

# # UUID namespace cố định
# NAMESPACE_LAW = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# class LegalEmbedder:
#     def __init__(self):
#         # Model BAAI/bge-m3 (dense size = 1024)
#         self.model = SentenceTransformer("BAAI/bge-m3", use_auth_token=HF_TOKEN)
#         self.collection = "legal_laws"

#         # DÙNG CLOUD: url + api_key + https
#         self.client = AsyncQdrantClient(
#             url=QDRANT_URL,
#             api_key=QDRANT_API_KEY,
#             timeout=60.0,
#         )

#     def generate_deterministic_uuid(self, string_id: str) -> str:
#         return str(uuid.uuid5(NAMESPACE_LAW, string_id))

#     async def init_collection(self):
#         # Tạo collection nếu chưa có
#         collections = await self.client.get_collections()
#         if not any(c.name == self.collection for c in collections.collections):
#             await self.client.create_collection(
#                 collection_name=self.collection,
#                 vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
#             )
#             # Tạo index cho payload (tối ưu filter)
#             # Lưu ý: dùng đúng type cho từng field
#             await self.client.create_payload_index(
#                 self.collection, "metadata.doc_info.doc_number", field_schema="keyword"
#             )
#             await self.client.create_payload_index(
#                 self.collection, "metadata.doc_info.year", field_schema="integer"
#             )
#             await self.client.create_payload_index(
#                 self.collection, "metadata.hierarchy.article_no", field_schema="integer"
#             )

#     def build_text(self, record: Dict) -> str:
#         m = record["metadata"]
#         title = m["doc_info"].get("title", "")
#         chapter = m["hierarchy"].get("chapter", "")
#         article_no = m["hierarchy"].get("article_no", "")
#         header = f"{title} | {chapter} | Điều {article_no}"
#         return f"{header}\n{record['content']}"

#     async def encode_texts(self, texts: List[str]):
#         # Đưa encode (blocking) sang threadpool để không chặn event loop
#         loop = asyncio.get_running_loop()
#         func = partial(self.model.encode, texts, normalize_embeddings=True)
#         vectors = await loop.run_in_executor(None, func)
#         return vectors

#     async def insert_batch(self, batch: List[Dict]):
#         texts = [self.build_text(r) for r in batch]
#         vectors = await self.encode_texts(texts)

#         points = []
#         for record, vector in zip(batch, vectors):
#             points.append(
#                 PointStruct(
#                     id=self.generate_deterministic_uuid(record["id"]),
#                     vector=vector.tolist(),
#                     payload={
#                         "content": record["content"],
#                         "metadata": record["metadata"],
#                         "raw_id": record["id"],
#                     },
#                 )
#             )

#         await self.client.upsert(collection_name=self.collection, points=points)

#     async def run(self, file_path: str):
#         await self.init_collection()

#         batch = []
#         BATCH_SIZE = 64
#         with open(file_path, "r", encoding="utf-8") as f:
#             for line in f:
#                 record = json.loads(line)
#                 batch.append(record)
#                 if len(batch) >= BATCH_SIZE:   # <-- sửa lại >=
#                     await self.insert_batch(batch)
#                     batch = []
#         if batch:
#             await self.insert_batch(batch)

#         print("Indexing completed!")

# if __name__ == "__main__":
#     # Kiểm tra biến môi trường trước khi chạy
#     if not QDRANT_URL or not QDRANT_API_KEY:
#         raise RuntimeError("Thiếu QDRANT_URL hoặc QDRANT_API_KEY. Hãy set biến môi trường trước.")
#     embedder = LegalEmbedder()
#     asyncio.run(embedder.run("laws_chunks_1_MH.jsonl"))



# -*- coding: utf-8 -*-
import json
import uuid
import asyncio
import os
from functools import partial
from typing import List, Dict

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from sentence_transformers import SentenceTransformer


HF_TOKEN = "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"  # tùy chọn, để tăng tốc HF

# UUID namespace cố định để ID deterministic
NAMESPACE_LAW = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

class LegalEmbedder:
    def __init__(self):
        # Model BAAI/bge-m3 (dense size = 1024)
        self.model = SentenceTransformer("BAAI/bge-m3", use_auth_token=HF_TOKEN)
        self.collection = "legal_laws"

        # KẾT NỐI QDRANT LOCAL (Docker) - KHÔNG api_key, dùng http
        self.client = AsyncQdrantClient(
            url="http://localhost:6333",
            timeout=60.0,
        )

    def generate_deterministic_uuid(self, string_id: str) -> str:
        return str(uuid.uuid5(NAMESPACE_LAW, string_id))

    async def init_collection(self):
        # Tạo collection nếu chưa có
        collections = await self.client.get_collections()
        if not any(c.name == self.collection for c in collections.collections):
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )

        # Tạo index cho payload (tối ưu filter). Bọc try/except để idempotent.
        try:
            await self.client.create_payload_index(
                self.collection, "metadata.doc_info.doc_number", field_schema="keyword"
            )
        except Exception:
            pass
        try:
            await self.client.create_payload_index(
                self.collection, "metadata.doc_info.year", field_schema="integer"
            )
        except Exception:
            pass
        try:
            await self.client.create_payload_index(
                self.collection, "metadata.hierarchy.article_no", field_schema="keyword"
            )
        except Exception:
            pass

    def build_text(self, record: Dict) -> str:
        m = record["metadata"]
        title = m["doc_info"].get("title", "")
        chapter = m["hierarchy"].get("chapter", "")
        article_no = m["hierarchy"].get("article_no", "")
        header = f"{title} | {chapter} | Điều {article_no}"
        return f"{header}\n{record['content']}"

    async def encode_texts(self, texts: List[str]):
        # Đưa encode (blocking) sang threadpool để không chặn event loop
        loop = asyncio.get_running_loop()
        func = partial(self.model.encode, texts, normalize_embeddings=True)
        vectors = await loop.run_in_executor(None, func)
        return vectors

    async def insert_batch(self, batch: List[Dict]):
        texts = [self.build_text(r) for r in batch]
        vectors = await self.encode_texts(texts)

        points = []
        for record, vector in zip(batch, vectors):
            points.append(
                PointStruct(
                    id=self.generate_deterministic_uuid(record["id"]),
                    vector=vector.tolist(),
                    payload={
                        "content": record["content"],
                        "metadata": record["metadata"],
                        "raw_id": record["id"],
                    },
                )
            )

        await self.client.upsert(collection_name=self.collection, points=points)

    async def run(self, file_path: str):
        await self.init_collection()

        batch = []
        BATCH_SIZE = 64
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                batch.append(record)
                if len(batch) >= BATCH_SIZE:  # <-- FIX: dùng >=
                    await self.insert_batch(batch)
                    batch = []
        if batch:
            await self.insert_batch(batch)

        print("Indexing completed!")

if __name__ == "__main__":
    embedder = LegalEmbedder()
    asyncio.run(embedder.run("laws_chunks_1_MH.jsonl"))