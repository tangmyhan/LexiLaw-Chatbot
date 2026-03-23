from uuid import uuid4
from time import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.db import get_redis, create_chat, chat_exists
from app.agents.assistant import LegalAssistant
from app.agents.tools import legal_tools

router = APIRouter()

class ChatIn(BaseModel):
    message: str

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
    
    if not await chat_exists(rdb, chat_id):
        await rdb.aclose()
        raise HTTPException(status_code=404, detail=f'Chat {chat_id} không tồn tại')
    
    message = chat_in.message.strip()
    if not message:
        await rdb.aclose()
        raise HTTPException(status_code=400, detail="Message không được rỗng")
    assistant = LegalAssistant(chat_id=chat_id, rdb=rdb)
    
    sse_stream = assistant.run(message=message)
    
    return EventSourceResponse(sse_stream, background=rdb.aclose)

@router.post('/chats/{chat_id}/graph')
async def get_graph_visualization(chat_id: str, chat_in: ChatIn):
    """Lấy dữ liệu visualization graph cho câu hỏi"""
    rdb = get_redis()
    
    if not await chat_exists(rdb, chat_id):
        await rdb.aclose()
        raise HTTPException(status_code=404, detail=f'Chat {chat_id} không tồn tại')
    
    message = chat_in.message.strip()
    if not message:
        await rdb.aclose()
        raise HTTPException(status_code=400, detail="Message không được rỗng")
    
    graph_data = await legal_tools.get_graph_visualization(message)
    await rdb.aclose()
    return graph_data