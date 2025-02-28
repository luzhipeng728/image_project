from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class User(BaseModel):
    username: str
    password: str
    created_at: Optional[datetime] = None
    is_admin: bool = False  # 添加管理员标志


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
    project_id: Optional[int] = None  # 添加项目ID关联


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
    project_id: Optional[int] = None  # 添加项目ID关联


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
    project_id: Optional[int] = None  # 添加项目ID关联

# 添加项目模型


class Project(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    owner_id: str  # 项目所有者用户名
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# 添加项目用户关联模型


class ProjectUser(BaseModel):
    id: Optional[int] = None
    project_id: int
    user_id: str  # 用户名
    can_edit: bool = False  # 是否有编辑权限
    can_generate: bool = True  # 是否有生成图片权限
    created_at: Optional[datetime] = None
