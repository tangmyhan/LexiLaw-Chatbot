# import google.generativeai as genai
# from app.core.config import settings

# # Cấu hình Google AI SDK
# genai.configure(api_key=settings.GEMINI_API_KEY)

# # Khởi tạo model instance
# llm_model = genai.GenerativeModel(
#     model_name=settings.GEMINI_MODEL,
#     # Bạn có thể thêm system_instruction ở đây hoặc trong Agent logic
# )

import google.generativeai as genai
from app.core.config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

def get_chat_model(system_instruction: str):
    # Sử dụng tính năng native của Gemini để giữ vai trò ổn định
    return genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        system_instruction=system_instruction
    )