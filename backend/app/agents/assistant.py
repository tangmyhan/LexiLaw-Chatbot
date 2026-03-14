import asyncio
from time import time
from app.agents.router import router_agent
from app.agents.researcher import ResearcherAgent
from app.agents.prompts import MAIN_SYSTEM_PROMPT, RAG_SYSTEM_PROMPT
from app.core.llm import get_chat_model  # Dùng wrapper mới
from app.utils.sse_stream import SSEStream
from app.db import add_chat_messages, get_chat_messages

class LegalAssistant:
    def __init__(self, chat_id, rdb, history_size=6):
        self.chat_id = chat_id
        self.rdb = rdb
        self.history_size = history_size
        self.researcher = ResearcherAgent()

    async def _handle_conversation_task(self, message: str, sse: SSEStream):
        try:
            start_time = time()
            # 1. Lấy và format lịch sử
            raw_history = await get_chat_messages(self.rdb, self.chat_id, last_n=self.history_size)
            # formatted_history = []
            # for h in raw_history:
            #     content = h.get("content", "").strip()
            #     if content:
            #         role = "model" if h["role"] == "assistant" else "user"
            #         formatted_history.append({"role": role, "parts": [h["content"]]})
            formatted_history = [
                {"role": "model" if h["role"] == "assistant" else "user", "parts": [h["content"]]}
                for h in raw_history if h.get("content") # Chỉ lấy tin nhắn có nội dung
        ]
            history_time = time() - start_time
            print(f"Thời gian lấy lịch sử: {history_time:.2f}s")

            # 2. Phân loại ý định và gather context song song
            intent_start = time()
            # Chạy song song cả 2 tác vụ
            intent_task = asyncio.create_task(router_agent.classify_intent(message, formatted_history[-2:] if formatted_history else []))
            context_task = asyncio.create_task(self.researcher.gather_all_evidence(message))
            
            # Đợi cả 2 cùng xong
            intent, context = await asyncio.gather(intent_task, context_task)
            intent_time = time() - intent_start
            print(f"Thời gian phân loại intent + gather context: {intent_time:.2f}s")

            # 3. Chuẩn bị System Instruction dựa trên Intent
            sys_inst = MAIN_SYSTEM_PROMPT
            if intent == "LEGAL_QUERY":
                context_str = "\n".join([f"[{d['source']}]: {d['content']}" for d in context])
                sys_inst = f"{RAG_SYSTEM_PROMPT}\n\nNGỮ CẢNH PHÁP LUẬT:\n{context_str}"

            # 4. Khởi tạo model với Instruction mới (Tối ưu cho từng turn)
            model_start = time()
            model = get_chat_model(system_instruction=sys_inst)
            chat_session = model.start_chat(history=formatted_history)
            model_time = time() - model_start
            print(f"Thời gian khởi tạo model: {model_time:.2f}s")

            # 5. Stream kết quả
            stream_start = time()
            full_response = ""
            async for chunk in await chat_session.send_message_async(message, stream=True):
                # Một số stream có thể gửi chunk rỗng; bỏ qua để tránh lỗi trong SSE
                if chunk.text and chunk.text.strip():
                    await sse.send(chunk.text)
                    full_response += chunk.text
            stream_time = time() - stream_start
            print(f"Thời gian stream response: {stream_time:.2f}s")

            # 6. Lưu vào Redis
            save_start = time()
            await add_chat_messages(self.rdb, self.chat_id, [
                {'role': 'user', 'content': message, 'created': int(time())},
                {'role': 'assistant', 'content': full_response, 'created': int(time())}
            ])
            save_time = time() - save_start
            print(f"Thời gian lưu Redis: {save_time:.2f}s")

            total_time = time() - start_time
            print(f"Tổng thời gian: {total_time:.2f}s")

        except Exception as e:
            await sse.send(f"Error: {str(e)}")
        finally:
            await sse.close()

    def run(self, message: str):
        sse = SSEStream()
        asyncio.create_task(self._handle_conversation_task(message, sse))
        return sse