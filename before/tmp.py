# -*- coding: utf-8 -*-
"""
verify_qdrant.py
Chạy 4 bài test tự động với Qdrant Cloud:
1) Kiểm tra schema (named vectors: "dense" 1024/COSINE + "text-sparse")
2) Đếm số points (exact)
3) Dense query test (dùng client.search với query_vector=("dense", vec))
4) Hybrid query test (prefetch dense + sparse và fusion=RRF; đọc res.points)

Yêu cầu biến môi trường:
- QDRANT_URL
- QDRANT_API_KEY
- (tuỳ chọn) HUGGINGFACE_HUB_TOKEN (token của HF)

Cài đặt:
pip install -U "qdrant-client[fastembed]" sentence-transformers python-dotenv

Chạy:
python verify_qdrant.py --collection legal_laws --top_k 5 \
  --query "nghỉ việc không báo trước bị phạt thế nào?"
"""

import os
import sys
import argparse
import json
from typing import Tuple, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

# ---------- ANSI helper ----------
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def ok(msg: str): print(f"{GREEN}✔ {msg}{RESET}")
def warn(msg: str): print(f"{YELLOW}⚠ {msg}{RESET}")
def fail(msg: str): print(f"{RED}✘ {msg}{RESET}")
def info(msg: str): print(f"{CYAN}ℹ {msg}{RESET}")

# ---------- Core checks ----------
def check_env() -> Tuple[str, str]:
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    print(f"QDRANT_URL = {url}")
    print(f"QDRANT_API_KEY (prefix) = {(api_key or '')[:6]}")

    if not url or not api_key:
        fail("Thiếu QDRANT_URL hoặc QDRANT_API_KEY trong môi trường.")
        sys.exit(1)
    return url, api_key

def _dump(obj: Any) -> str:
    try:
        return json.dumps(obj.model_dump(), ensure_ascii=False, indent=2)
    except Exception:
        try:
            return json.dumps(obj.dict(), ensure_ascii=False, indent=2)
        except Exception:
            return str(obj)

def check_collection_schema(client: QdrantClient, collection: str) -> bool:
    """
    PASS nếu:
      - Có named vector "dense" size=1024, distance=Cosine
      - Có sparse named "text-sparse" (không bắt buộc để pass tối thiểu, nhưng sẽ WARN)
    """
    info = client.get_collection(collection)

    # params theo SDK mới: info.config.params
    params = getattr(info, "config", None)
    params = getattr(params, "params", None)

    passed = True

    # Dense
    dense_named_ok = False
    vectors = getattr(params, "vectors", None)
    if isinstance(vectors, dict):
        if "dense" in vectors:
            v = vectors["dense"]
            size = getattr(v, "size", None) or (v.get("size") if isinstance(v, dict) else None)
            distance = getattr(v, "distance", None) or (v.get("distance") if isinstance(v, dict) else None)
            dense_named_ok = (size == 1024) and (str(distance).lower().endswith("cosine"))
    elif vectors is not None:
        # single vector (không tên)
        v = vectors
        size = getattr(v, "size", None)
        distance = getattr(v, "distance", None)
        if size == 1024 and str(distance).lower().endswith("cosine"):
            warn('Schema: Collection đang dùng single vector (không tên). Nên dùng named "dense" cho Hybrid.')
            dense_named_ok = True

    if dense_named_ok:
        ok('Schema: Dense "dense" = 1024/COSINE (hoặc single vector tương đương).')
    else:
        passed = False
        fail('Schema: Thiếu hoặc sai cấu hình dense (yêu cầu named "dense" 1024/COSINE).')

    # Sparse
    sparse_ok = False
    sparse_vectors = getattr(params, "sparse_vectors", None)
    if isinstance(sparse_vectors, dict) and "text-sparse" in sparse_vectors:
        ok('Schema: Có sparse named "text-sparse"')
        sparse_ok = True
    else:
        warn('Schema: Chưa thấy sparse named "text-sparse" (Hybrid sẽ hạn chế cho tới khi nạp sparse).')

    return passed

def count_points(client: QdrantClient, collection: str) -> int:
    cnt = client.count(collection, exact=True)
    n = getattr(cnt, "count", None) or cnt
    ok(f"Points: {n} (exact)")
    return int(n)

# ---------- Embedding ----------
def x() -> SentenceTransformer:
    # Không dùng use_auth_token để tránh warning deprecated.
    # Nếu có token HF, đặt env HUGGINGFACE_HUB_TOKEN hoặc login huggingface_hub.
    try:
        model = SentenceTransformer("BAAI/bge-m3")
        ok("Tải model BAAI/bge-m3 thành công.")
        return model
    except Exception as e:
        fail(f"Lỗi tải BAAI/bge-m3: {e}")
        sys.exit(1)

def encode_query(embedder: SentenceTransformer, text: str):
    return embedder.encode([text], normalize_embeddings=True)[0].tolist()

# ---------- Tests ----------
def test_dense_query(client: QdrantClient, collection: str, embedder: SentenceTransformer, query_text: str, top_k: int = 5) -> bool:
    """
    Dense test qua Query API để tương thích mọi version qdrant-client.
    - Gửi vector chính (query=vec) + using="dense"
    - Lấy kết quả từ res.points (hoặc res.result)
    """
    vec = encode_query(embedder, query_text)
    try:
        res = client.query_points(
            collection_name=collection,
            query=vec,          # <-- vector dense
            using="dense",      # <-- tên named vector
            limit=top_k,
            with_payload=True,
        )
        hits = getattr(res, "points", None) or getattr(res, "result", None) or []
        if not hits:
            fail("Dense Query: Không có kết quả.")
            return False

        ok(f"Dense Query: Trả về {len(hits)} kết quả.")
        for i, h in enumerate(hits[:2], 1):
            src = h.payload.get("metadata", {}).get("doc_info", {}).get("title", "(no-title)") if isinstance(h.payload, dict) else "(no-payload)"
            content = h.payload.get('content') or ''
            print(f"  {i:>2}. id={h.id} score={h.score:.4f}  title={src}")
            print(f"   Nội dung: {content[:200]}...\n")
        return True
    except Exception as e:
        fail(f"Dense Query: Lỗi khi truy vấn - {e}")
        return False

def test_hybrid_query(client: QdrantClient, collection: str, embedder: SentenceTransformer, query_text: str, top_k: int = 5) -> bool:
    """
    Hybrid = 2 prefetch (sparse BM25 + dense) rồi fusion=RRF.
    query_points trả về QueryResponse -> đọc res.points (hoặc res.result tuỳ version).
    """
    vec = encode_query(embedder, query_text)
    try:
        res = client.query_points(
            collection_name=collection,
            prefetch=[
                # Sparse (BM25) vào named "text-sparse"
                models.Prefetch(
                    query=models.Document(text=query_text, model="Qdrant/bm25"),
                    using="text-sparse",
                    limit=max(top_k * 3, 20),
                ),
                # Dense vào named "dense"
                models.Prefetch(
                    query=vec,
                    using="dense",
                    limit=max(top_k * 3, 20),
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        hits = getattr(res, "points", None) or getattr(res, "result", None) or []
        n = len(hits)
        if n == 0:
            warn("Hybrid Query: 0 kết quả. Có thể do nhánh sparse chưa có dữ liệu hoặc bộ dữ liệu còn ít.")
            return False

        ok(f"Hybrid Query (RRF): Trả về {n} kết quả.")
        for i, h in enumerate(hits[:2], 1):
            src = h.payload.get("metadata", {}).get("doc_info", {}).get("title", "(no-title)") if isinstance(h.payload, dict) else "(no-payload)"
            content = h.payload.get('content') or ''
            print(f"  {i:>2}. id={h.id} score={h.score:.4f}  title={src}")
            print(f"   Nội dung: {content[:200]}...\n")
        return True
    except Exception as e:
        warn(f"Hybrid Query: Lỗi khi truy vấn Hybrid - {e}")
        return False

# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser(description="Verify Qdrant Cloud setup for legal chatbot")
    parser.add_argument("--collection", default="legal_laws", help="Tên collection cần kiểm tra")
    parser.add_argument("--top_k", type=int, default=5, help="Số kết quả trả về")
    parser.add_argument("--query", default="mức lương tối thiểu ở thành phố Hồ Chí Minh", help="Câu hỏi test")
    args = parser.parse_args()

    print(f"{BOLD}=== Qdrant Cloud Verify ==={RESET}")
    url, api_key = check_env()
    info(f"Cluster: {url}")
    info(f"Collection: {args.collection}")

    client = QdrantClient(url=url, api_key=api_key, timeout=60.0)

    # 1) Schema
    print(f"{BOLD}\n[1] Kiểm tra schema{RESET}")
    schema_ok = check_collection_schema(client, args.collection)

    # 2) Count
    print(f"{BOLD}\n[2] Đếm points{RESET}")
    total_points = count_points(client, args.collection)
    if total_points == 0:
        warn("Collection chưa có dữ liệu (0 points). Dense/Hybrid query có thể không trả kết quả.")

    # 3) Dense query
    print(f"{BOLD}\n[3] Dense query test{RESET}")
    embedder = build_embedder()
    dense_ok = test_dense_query(client, args.collection, embedder, args.query, args.top_k)

    # 4) Hybrid query
    print(f"{BOLD}\n[4] Hybrid query test (Dense + BM25 via RRF){RESET}")
    hybrid_ok = test_hybrid_query(client, args.collection, embedder, args.query, args.top_k)

    print(f"{BOLD}\n=== KẾT LUẬN ==={RESET}")
    if schema_ok and dense_ok:
        ok("Hệ thống hoạt động ở mức Dense (ít nhất).")
    else:
        fail("Thiếu điều kiện tối thiểu (schema hoặc dense query lỗi).")

    if hybrid_ok:
        ok("Hybrid Query hoạt động. (Đã fuse kết quả trên server bằng RRF).")
    else:
        warn("Hybrid Query chưa hoạt động đầy đủ. Có thể bạn CHƯA nạp sparse vectors.\n"
             "👉 Gợi ý: Khi upsert, thêm nhánh sparse:\n"
             "   vector={ 'dense': <list[float]>, 'text-sparse': models.Document(text=..., model='Qdrant/bm25') }\n"
             "   hoặc nạp SparseVector(indices, values) từ SPLADE/BGE-M3 sparse head.")

if __name__ == "__main__":
    main()