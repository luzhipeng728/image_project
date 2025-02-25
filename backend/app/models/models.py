from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class User(BaseModel):
    username: str
    password: str
    created_at: Optional[datetime] = None

class Model(BaseModel):
    id: Optional[int] = None
    name: str
    alias: str
    mapping_name: Optional[str] = None
    original_price: float = 0
    current_price: float = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Image(BaseModel):
    id: Optional[int] = None
    file_path: str
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    created_at: Optional[datetime] = None

class TextToImageGeneration(BaseModel):
    id: Optional[int] = None
    username: str
    model_id: int
    prompt: str
    seed: Optional[int] = None
    width: int = 1024
    height: int = 1024
    enhance: bool = False
    image_id: Optional[int] = None
    status: str = "pending"
    created_at: Optional[datetime] = None

class ImageToImageGeneration(BaseModel):
    id: Optional[int] = None
    username: str
    model_id: int
    prompt: Optional[str] = None
    prompt_image_id: int
    seed: Optional[int] = None
    width: int = 1024
    height: int = 1024
    enhance: bool = False
    image_id: Optional[int] = None
    status: str = "pending"
    created_at: Optional[datetime] = None 