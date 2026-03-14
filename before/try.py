import json
import uuid
import asyncio
import os
from functools import partial
from typing import List, Dict

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, SparseVectorParams, SparseIndexParams
from sentence_transformers import SentenceTransformer


from dotenv import load_dotenv
load_dotenv()


QDRANT_URL = os.getenv("QDRANT_URL") 
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")  

NAMESPACE_LAW = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

class LegalEmbedder:
    def __init__(self):
        self.model = SentenceTransformer("BAAI/bge-m3", use_auth_token=HF_TOKEN)
        self.collection = "legal_laws"
        self.client = AsyncQdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            timeout=120.0,
        )

    def generate_deterministic_uuid(self, string_id: str) -> str:
        return str(uuid.uuid5(NAMESPACE_LAW, string_id))

    # async def init_collection(self):
    #     collections = await self.client.get_collections()
    #     if not any(c.name == self.collection for c in collections.collections):
    #         await self.client.create_collection(
    #             collection_name=self.collection,
    #             vectors_config={
    #                 "dense": VectorParams(size=1024, distance=Distance.COSINE)
    #             },
    #             sparse_vectors_config={
    #                 "text-sparse": SparseVectorParams(index=SparseIndexParams(on_disk=True))
    #             }
    #         )
    #         print(f"Created collection: {self.collection}")

    
    async def init_collection(self, force_recreate: bool = True):
        # By default recreate collection, but when resuming we skip recreation to preserve data.
        if force_recreate:
            await self.client.recreate_collection(
                collection_name=self.collection,
                vectors_config={"dense": VectorParams(size=1024, distance=Distance.COSINE)},
                sparse_vectors_config={
                    "text-sparse": SparseVectorParams(index=SparseIndexParams(on_disk=True))
                },
            )
            print(f"Recreated collection: {self.collection}")
        else:
            # Ensure collection exists; create if missing
            try:
                exists = await self.client.get_collection(collection_name=self.collection)
                print(f"Collection exists: {self.collection}")
            except Exception:
                await self.client.create_collection(
                    collection_name=self.collection,
                    vectors_config={"dense": VectorParams(size=1024, distance=Distance.COSINE)},
                    sparse_vectors_config={
                        "text-sparse": SparseVectorParams(index=SparseIndexParams(on_disk=True))
                    },
                )
                print(f"Created collection: {self.collection}")


        # Indexing Payload (Idempotent)
        index_configs = [
            ("metadata.doc_info.doc_number", "keyword"),
            ("metadata.doc_info.year", "integer"),
            ("metadata.hierarchy.article_no", "keyword") # Đã sửa thành keyword cho Điều 70a, 70b...
        ]
        
        for field, schema in index_configs:
            try:
                await self.client.create_payload_index(self.collection, field, field_schema=schema)
            except Exception: pass

    def build_text(self, record: Dict) -> str:
        m = record["metadata"]
        header = f"{m['doc_info'].get('title', '')} | {m['hierarchy'].get('chapter', '')} | Điều {m['hierarchy'].get('article_no', '')}"
        return f"{header}\n{record['content']}"

    async def encode_texts(self, texts: List[str]):
        loop = asyncio.get_running_loop()
        func = partial(self.model.encode, texts, normalize_embeddings=True)
        return await loop.run_in_executor(None, func)

    async def upsert_with_retry(self, points, retries: int = 4, base_delay: float = 1.0):
        for attempt in range(1, retries + 1):
            try:
                await self.client.upsert(collection_name=self.collection, points=points)
                return
            except Exception as e:
                if attempt == retries:
                    raise
                await asyncio.sleep(base_delay * (2 ** (attempt - 1)))

    async def insert_batch(self, batch: List[Dict]):
        texts = [self.build_text(r) for r in batch]
        vectors = await self.encode_texts(texts)

        points = []
        for record, vector in zip(batch, vectors):
            points.append(
                PointStruct(
                    id=self.generate_deterministic_uuid(record["id"]),
                    vector={"dense": vector.tolist()}, # Bắt buộc dùng dict cho named vectors
                    payload={
                        "content": record["content"],
                        "metadata": record["metadata"],
                        "raw_id": record["id"],
                    },
                )
            )
        await self.upsert_with_retry(points)

    async def run(self, file_path: str):
        # Support resume: use a progress file to store last processed line number.
        progress_path = f"{file_path}.progress.json"
        start_line = 1
        if os.path.exists(progress_path):
            try:
                with open(progress_path, "r", encoding="utf-8") as pf:
                    data = json.load(pf)
                    start_line = int(data.get("last_line", 0)) + 1
                print(f"Resuming from line {start_line} (progress file found). Will NOT recreate collection.")
                await self.init_collection(force_recreate=False)
            except Exception:
                print("Failed to read progress file; starting from beginning and recreating collection.")
                await self.init_collection(force_recreate=True)
        else:
            # fresh run: recreate collection
            await self.init_collection(force_recreate=True)

        batch: List[Dict] = []
        BATCH_SIZE = 32
        last_processed = start_line - 1
        line_no = 0
        with open(file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                if line_no < start_line:
                    continue
                if not line.strip():
                    continue
                try:
                    batch.append(json.loads(line))
                except Exception:
                    # skip malformed line but remember position
                    last_processed = line_no
                    continue

                last_processed = line_no
                if len(batch) >= BATCH_SIZE:
                    await self.insert_batch(batch)
                    # checkpoint
                    with open(progress_path, "w", encoding="utf-8") as pf:
                        json.dump({"last_line": last_processed}, pf)
                    batch = []

        if batch:
            await self.insert_batch(batch)
            with open(progress_path, "w", encoding="utf-8") as pf:
                json.dump({"last_line": last_processed}, pf)

        print("Indexing completed!")

if __name__ == "__main__":
    print("QDRANT_URL =", os.getenv("QDRANT_URL"))
    print("QDRANT_API_KEY (prefix) =", (os.getenv("QDRANT_API_KEY") or "")[:6])
    embedder = LegalEmbedder()
    asyncio.run(embedder.run("laws_chunks_1_MH.jsonl"))
    
