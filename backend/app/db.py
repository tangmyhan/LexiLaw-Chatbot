import json
from time import time
from typing import List, Dict
import redis.asyncio as redis
from app.core.config import settings

# Khởi tạo Redis connection pool
def get_redis():
    return redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        encoding="utf-8"
    )

async def create_chat(rdb: redis.Redis, chat_id: str, created_at: int):
    """Khởi tạo một phiên chat mới"""
    await rdb.hset(f"chat:{chat_id}", "created", created_at)

async def chat_exists(rdb: redis.Redis, chat_id: str) -> bool:
    """Kiểm tra phiên chat có tồn tại không"""
    return await rdb.exists(f"chat:{chat_id}")

async def add_chat_messages(rdb: redis.Redis, chat_id: str, messages: List[Dict]):
    """Thêm tin nhắn mới vào lịch sử (Redis List)"""
    key = f"chat:{chat_id}:messages"
    for msg in messages:
        await rdb.rpush(key, json.dumps(msg))
    # Đặt thời gian hết hạn cho lịch sử chat (ví dụ 24h)
    await rdb.expire(f"chat:{chat_id}", 86400)
    await rdb.expire(key, 86400)

async def get_chat_messages(rdb: redis.Redis, chat_id: str, last_n: int = 10) -> List[Dict]:
    """Lấy N tin nhắn gần nhất để làm ngữ cảnh cho LLM"""
    key = f"chat:{chat_id}:messages"
    # Lấy từ cuối danh sách
    raw_messages = await rdb.lrange(key, -last_n, -1)
    return [json.loads(m) for m in raw_messages]


def format_for_gemini(messages: List[Dict]) -> List[Dict]:
    """Chuyển đổi format từ DB sang format Gemini hiểu được"""
    gemini_msgs = []
    for msg in messages:
        # Gemini dùng 'model' thay vì 'assistant'
        role = "model" if msg["role"] == "assistant" else "user"
        gemini_msgs.append({"role": role, "parts": [msg["content"]]})
    return gemini_msgs