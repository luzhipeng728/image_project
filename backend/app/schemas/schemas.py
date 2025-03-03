from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

# Auth schemas


class UserCreate(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    username: str
    created_at: Optional[datetime] = None
    is_admin: bool = False


class UserAdminUpdate(BaseModel):
    is_admin: bool


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
    project_id: Optional[int] = None


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
    id: UUID
    status: str
    image_url: Optional[str] = None
    project_id: Optional[int] = None


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
    project_id: Optional[int] = None

# Image schemas


class ImageResponse(BaseModel):
    id: int
    file_path: str
    width: Optional[int]
    height: Optional[int]
    file_type: Optional[str]
    project_id: Optional[int] = None


class ImageUploadRequest(BaseModel):
    project_id: Optional[int] = None
    overwrite: bool = False

# Project schemas


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    owner_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

class BatchTaskStatus(BaseModel):
    task_id: int
    status: str
    total_images: int
    completed_images: int
    created_at: str
    updated_at: str
    error: Optional[str] = None

class BatchGenerationRequest(BaseModel):
    prompt: str
    model_id: int
