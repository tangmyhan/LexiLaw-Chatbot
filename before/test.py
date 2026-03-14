import os
import asyncio
from qdrant_client import AsyncQdrantClient
from sentence_transformers import SentenceTransformer

from dotenv import load_dotenv
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL") 
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")  


async def verify_qdrant():
    # Cấu hình từ môi trường
    client = AsyncQdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY")
    )
    
    # Load model để tạo vector cho câu hỏi (Query)
    model = SentenceTransformer("BAAI/bge-m3")
    collection_name = "legal_laws"

    # 1. Kiểm tra số lượng bản ghi
    info = await client.get_collection(collection_name=collection_name)
    print(f"--- THÔNG TIN COLLECTION ---")
    print(f"Số lượng bản ghi hiện có: {info.points_count}")
    print(f"Trạng thái: {info.status}\n")

    # 2. Thử nghiệm tìm kiếm ngữ nghĩa
    query_text = "Quy định về hợp đồng lao động điện tử?"
    # Lưu ý: BGE-M3 không bắt buộc nhưng nên dùng prefix nếu model yêu cầu
    query_vector = model.encode(query_text, normalize_embeddings=True).tolist()

    search_result = await client.query_points(
        collection_name=collection_name,
        query=query_vector,
        using="dense",  # use named vector 'dense'
        limit=3,
        with_payload=True,
    )

    print(f"--- KẾT QUẢ TÌM KIẾM CHO: '{query_text}' ---")
    for i, res in enumerate(search_result.points):
        payload = res.payload or {}
        metadata = payload.get("metadata", {})
        doc_info = metadata.get("doc_info", {})
        print(f"{i+1}. [Score: {res.score:.4f}]")
        print(f"   Văn bản: {doc_info.get('title')} ({doc_info.get('doc_number')})")
        content = payload.get('content') or ''
        print(f"   Nội dung: {content[:200]}...\n")

if __name__ == "__main__":
    asyncio.run(verify_qdrant())

    
print("QDRANT_URL =", os.getenv("QDRANT_URL"))
print("QDRANT_API_KEY (prefix) =", (os.getenv("QDRANT_API_KEY") or "")[:6])
