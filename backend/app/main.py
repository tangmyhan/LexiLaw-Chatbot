from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import router
from app.core.config import settings
from app.db import get_redis

# Quản lý vòng đời ứng dụng (Lifespan)
@asynccontextmanager
async def lifespan(app: FastAPI):
    rdb = get_redis()
    try:
        await rdb.ping()
        print("Kết nối Redis thành công!")
    except Exception as e:
        print(f"Lỗi kết nối Redis: {e}")
    finally:
        await rdb.aclose()
        
    yield
    
    print("Tắt server LawRAG...")

app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan
)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS if hasattr(settings, 'ALLOW_ORIGINS') else ["*"],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(router)

@app.head('/health')
@app.get('/health')
def health_check():
    """Kiểm tra trạng thái server"""
    return 'ok'

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)