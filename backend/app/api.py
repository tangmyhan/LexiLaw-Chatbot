from uuid import uuid4
from time import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.db import get_redis, create_chat, chat_exists
from app.agents.manager import RAGAssistant

router = APIRouter()

class ChatIn(BaseModel):
    message: str

# Dependency để lấy Redis client
async def get_rdb():
    rdb = get_redis()
    try:
        yield rdb
    finally:
        await rdb.aclose()

@router.post('/chats')
async def create_new_chat(rdb = Depends(get_rdb)):
    """Tạo session ID mới cho người dùng"""
    chat_id = str(uuid4())[:8]
    created = int(time())
    await create_chat(rdb, chat_id, created)
    return {'id': chat_id}

@router.post('/chats/{chat_id}')
async def chat(chat_id: str, chat_in: ChatIn):
    """Endpoint chính để chat, hỗ trợ Streaming SSE"""
    rdb = get_redis()
    
    # Kiểm tra session
    if not await chat_exists(rdb, chat_id):
        await rdb.aclose()
        raise HTTPException(status_code=404, detail=f'Chat {chat_id} không tồn tại')
    
    # Khởi tạo Assistant với logic Search -> Rerank -> Gemini
    # Chúng ta truyền Redis client vào để Assistant tự quản lý lịch sử
    assistant = RAGAssistant(chat_id=chat_id, rdb=rdb)
    
    # Hàm run của Assistant sẽ trả về một SSEStream object
    sse_stream = assistant.run(message=chat_in.message)
    
    # Trả về stream cho Frontend, đóng kết nối Redis sau khi hoàn thành
    return EventSourceResponse(sse_stream, background=rdb.aclose)