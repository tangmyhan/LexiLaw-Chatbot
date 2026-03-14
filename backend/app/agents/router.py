from app.core.llm import get_chat_model
from app.agents.prompts import ROUTER_PROMPT

class RouterAgent:
    async def classify_intent(self, user_query: str, history: list = []) -> str:
        history_context = ""
        if history:
            history_context = "Lịch sử gần đây:\n" + "\n".join([f"{m['role']}: {m['parts'][0]}" for m in history])
        
        prompt = f"{ROUTER_PROMPT}\n\n{history_context}\nCâu hỏi hiện tại: {user_query}"
        model = get_chat_model("")  # Không cần system_instruction cho router
        response = await model.generate_content_async(prompt)
        intent = response.text.strip().upper()
        return intent if intent in ["LEGAL_QUERY", "GENERAL_CHAT"] else "LEGAL_QUERY"

router_agent = RouterAgent()