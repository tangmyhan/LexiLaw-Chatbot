import asyncio
from time import time
from app.agents.router import router_agent
from app.agents.researcher import ResearcherAgent
from app.agents.prompts import MAIN_SYSTEM_PROMPT, RAG_SYSTEM_PROMPT, ANSWER_PROMPT
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
            # 1. Lấy và format lịch sử
            raw_history = await get_chat_messages(self.rdb, self.chat_id, last_n=self.history_size)
            formatted_history = []
            for h in raw_history:
                role = "model" if h["role"] == "assistant" else "user"
                formatted_history.append({"role": role, "parts": [h["content"]]})

            # 2. Phân loại ý định (Truyền thêm lịch sử để Router hiểu ngữ cảnh)
            intent = await router_agent.classify_intent(message, formatted_history[-2:] if formatted_history else [])

            # 3. Chuẩn bị System Instruction dựa trên Intent
            sys_inst = MAIN_SYSTEM_PROMPT
            if intent == "LEGAL_QUERY":
                context = await self.researcher.gather_all_evidence(message)
                context_str = "\n".join([f"[{d['source']}]: {d['content']}" for d in context])
                sys_inst = f"{RAG_SYSTEM_PROMPT}\n\nNGỮ CẢNH PHÁP LUẬT:\n{context_str}"

            # 4. Khởi tạo model với Instruction mới (Tối ưu cho từng turn)
            model = get_chat_model(system_instruction=sys_inst)
            chat_session = model.start_chat(history=formatted_history)

            # 5. Stream kết quả
            full_response = ""
            async for chunk in await chat_session.send_message_async(message, stream=True):
                if chunk.text:
                    await sse.send(chunk.text)
                    full_response += chunk.text

            # 6. Lưu vào Redis
            await add_chat_messages(self.rdb, self.chat_id, [
                {'role': 'user', 'content': message, 'created': int(time())},
                {'role': 'assistant', 'content': full_response, 'created': int(time())}
            ])

        except Exception as e:
            await sse.send(f"Error: {str(e)}")
        finally:
            await sse.close()

    def run(self, message: str):
        sse = SSEStream()
        asyncio.create_task(self._handle_conversation_task(message, sse))
        return sse