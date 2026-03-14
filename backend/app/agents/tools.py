# from pydantic import BaseModel, Field
# from app.db import search_vector_db
# from app.openai import get_embedding

# class QueryKnowledgeBaseTool(BaseModel):
#     """Query the knowledge base to answer user questions about new technology trends, their applications and broader impacts."""
#     query_input: str = Field(description='The natural language query input string. The query input should be clear and standalone.')

#     async def __call__(self, rdb):
#         query_vector = await get_embedding(self.query_input)
#         chunks = await search_vector_db(rdb, query_vector)
#         formatted_sources = [f"SOURCE: {c['doc_name']}\n\"\"\"\n{c['text']}\n\"\"\"" for c in chunks]
#         return f"\n\n---\n\n".join(formatted_sources) + f"\n\n---"


from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, Field, ConfigDict
from app.db import search_vector_db  # (rdb, query_vector, top_k=..., with_payload=..., **kwargs) -> List[Dict]
from app.openai import get_embedding  # (text: str) -> List[float]
# Optional: từ app.rerank import rerank_chunks  # (query, chunks, top_k) -> List[Dict]

class QueryKnowledgeBaseTool(BaseModel):
    """
    Truy vấn Knowledge Base bằng vector search (và tùy chọn rerank) để lấy các đoạn văn bản liên quan.
    Dùng cho RAG/QA. Kết quả trả về là chuỗi đã format gồm nhiều SOURCE.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)  # Cho phép rdb là object client tùy ý

    query_input: str = Field(
        description="Câu hỏi ngôn ngữ tự nhiên, rõ ràng và độc lập ngữ cảnh.",
        min_length=1,
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Số lượng chunk tối đa lấy từ vector DB."
    )
    max_chars_per_chunk: int = Field(
        default=1800,
        ge=200,
        le=8000,
        description="Giới hạn ký tự mỗi chunk để tránh tràn token."
    )
    enable_rerank: bool = Field(
        default=False,
        description="Bật reranking (VD: BAAI/bge-reranker-v2-m3) sau bước vector retrieval."
    )
    # Các filter/collections... có thể thêm tùy domain: collection_name, filters, time_range, doc_types...

    async def __call__(self, rdb: Any) -> str:
        # 1) Embedding
        try:
            query_vector = await get_embedding(self.query_input)
        except Exception as e:
            return f"[EmbeddingError] Không tạo được embedding cho truy vấn: {e}"

        # 2) Vector search
        try:
            # Bạn có thể mở rộng search_vector_db để nhận top_k, filters, vv.
            chunks: List[Dict[str, Any]] = await search_vector_db(
                rdb=rdb,
                query_vector=query_vector,
                top_k=self.top_k,
                with_payload=True,
            )
        except Exception as e:
            return f"[SearchError] Lỗi khi truy vấn vector DB: {e}"

        # 3) (Optional) Rerank
        # if self.enable_rerank:
        #     chunks = await rerank_chunks(self.query_input, chunks, top_k=self.top_k)

        if not chunks:
            return "[NoResults] Không tìm thấy đoạn văn bản liên quan."

        # 4) Chuẩn hóa & cắt độ dài mỗi chunk
        formatted_sources: List[str] = []
        for c in chunks:
            doc_name = str(c.get("doc_name", "UNKNOWN_SOURCE"))
            text = str(c.get("text", "")).strip()

            if not text:
                # Bỏ qua chunk rỗng
                continue

            if len(text) > self.max_chars_per_chunk:
                # Cắt gọn, giữ head (bạn có thể dùng head + tail nếu cần)
                text = text[: self.max_chars_per_chunk] + " ..."

            block = f"SOURCE: {doc_name}\n\"\"\"\n{str(text)}\n\"\"\""
            formatted_sources.append(block)

        if not formatted_sources:
            return "[NoUsableChunks] Có kết quả nhưng payload thiếu 'text'."

        return "\n\n---\n\n".join(formatted_sources) + "\n\n---"