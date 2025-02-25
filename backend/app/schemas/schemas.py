from typing import Optional, List
from pydantic import BaseModel

# Auth schemas
class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Model schemas
class ModelCreate(BaseModel):
    name: str
    alias: str
    mapping_name: Optional[str] = None
    original_price: float = 0
    current_price: float = 0

class ModelResponse(BaseModel):
    id: int
    name: str
    alias: str
    mapping_name: Optional[str] = None
    current_price: float

# Generation schemas
class GenerationBase(BaseModel):
    model_id: int
    seed: Optional[int] = 1
    width: int = 1024
    height: int = 1024
    enhance: bool = False

class TextToImageRequest(GenerationBase):
    prompt: str

class ImageToImageRequest(GenerationBase):
    prompt: Optional[str] = None
    image_url: str
    model_id: Optional[int] = None
    seed: Optional[int] = 42
    width: Optional[int] = None
    height: Optional[int] = None
    enhance: Optional[bool] = None
    gen_seed: Optional[int] = 42

class GenerationResponse(BaseModel):
    id: int
    status: str
    image_url: Optional[str] = None

class GenerationHistoryResponse(BaseModel):
    id: int
    prompt: Optional[str]
    model_name: str
    seed: Optional[int]
    width: int
    height: int
    enhance: bool
    status: str
    image_url: Optional[str]
    created_at: str

# Image schemas
class ImageResponse(BaseModel):
    id: int
    file_path: str
    width: Optional[int]
    height: Optional[int]
    file_type: Optional[str] 