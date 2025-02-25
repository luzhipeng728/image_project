from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .database.database import init_db
from .api.endpoints import auth, generation
from .api.endpoints.generation import router as generation_router
from .api.endpoints.generation import image_router
import logging
logging.basicConfig(level=logging.DEBUG)

# 初始化数据库
init_db()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# 注册路由
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(
    generation_router,
    prefix=f"{settings.API_V1_STR}/generation",
    tags=["generation"]
)
app.include_router(
    image_router,
    tags=["images"]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 