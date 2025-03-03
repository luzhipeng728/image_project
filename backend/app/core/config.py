import os
from typing import Optional


class Settings:
    PROJECT_NAME: str = "Image Generation Service"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"

    # JWT设置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 3000

    # 图片生成API设置
    DEEPINFRA_API_URL: str = "https://api.deepinfra.com/v1/openai/images/generations"
    DEEPINFRA_API_KEY: str = os.getenv(
        "DEEPINFRA_API_KEY", "it4UO7bizCjvKEbtxEGhkOQGCwsQlyag")
    HYPRLAB_API_KEY: str = os.getenv(
        "HYPRLAB_API_KEY", "hypr-lab-AhlUmIPK999Z51T1zq3sT3BlbkFJMtsLVnBefsOcvFSJSlNV")

    # 文件存储设置
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_FILE_TYPES: list = ["image/jpeg", "image/png", "image/gif"]

    # 缓存设置
    DEFAULT_SEED: int = 42
    DEFAULT_WIDTH: int = 1024
    DEFAULT_HEIGHT: int = 1024
    DEFAULT_ENHANCE: bool = False
    BACKEND_URL: str = "http://localhost:8002"


settings = Settings()
