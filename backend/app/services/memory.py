import json
import hashlib
from typing import List, Dict, Any, Optional
from app.core.redis import redis_client

class MemoryService:
    def __init__(self, ttl: int = 3600):  # TTL mặc định 1 giờ
        self.ttl = ttl

    def _get_cache_key(self, query: str) -> str:
        """Tạo key cache từ query (hash để tránh key quá dài)"""
        return f"cache:query:{hashlib.md5(query.encode()).hexdigest()}"

    async def get_cached_result(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Lấy kết quả cached nếu có"""
        key = self._get_cache_key(query)
        cached = await redis_client.get(key)
        if cached:
            return json.loads(cached)
        return None

    async def set_cached_result(self, query: str, result: List[Dict[str, Any]]):
        """Lưu kết quả vào cache"""
        key = self._get_cache_key(query)
        await redis_client.setex(key, self.ttl, json.dumps(result))

    async def invalidate_cache(self, query: str):
        """Xóa cache cho query cụ thể"""
        key = self._get_cache_key(query)
        await redis_client.delete(key)

memory_service = MemoryService()