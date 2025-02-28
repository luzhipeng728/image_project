from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from ..services.image_service import ImageService
from ..services.queue.queue_service import QueueService
from ..models.models import User
from ..core.auth import get_current_user
from pydantic import BaseModel, Field

router = APIRouter()


@router.get("/history")
async def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    generation_type: Optional[str] = Query(
        None, regex="^(text_to_image|image_to_image)$"),
    current_user: User = Depends(get_current_user)
):
    """获取用户的图片生成历史记录"""
    try:
        history = await ImageService.get_generation_history(
            username=current_user.username,
            page=page,
            page_size=page_size,
            generation_type=generation_type
        )
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 队列相关模型


class QueueTask(BaseModel):
    image_id: int
    image_url: str
    prompt: str
    width: Optional[int] = None
    height: Optional[int] = None
    seeds: List[int] = Field(default_factory=list)
    source_image_path: str


class CreateQueueRequest(BaseModel):
    tasks: List[QueueTask]
    model_id: int
    project_id: int
    concurrency: int = 5


class QueueResponse(BaseModel):
    queue_id: str


class ActiveQueuesResponse(BaseModel):
    queues: List[Dict[str, Any]]


@router.post("/create-queue", response_model=QueueResponse)
async def create_generation_queue(
    request: CreateQueueRequest,
    current_user: User = Depends(get_current_user)
):
    """创建图像生成队列"""
    try:
        # 验证并限制并发数
        concurrency = max(1, min(10, request.concurrency))

        # 创建队列
        queue_id = QueueService.create_generation_queue(
            user_id=current_user.username,
            tasks=[task.dict() for task in request.tasks],
            model_id=request.model_id,
            project_id=request.project_id,
            concurrency=concurrency
        )

        if queue_id is None:
            raise HTTPException(
                status_code=429,
                detail="已达到最大队列数量限制，请等待其他队列完成后再试"
            )

        return {"queue_id": queue_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue-status/{queue_id}")
async def get_queue_status(
    queue_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取队列状态"""
    try:
        status = QueueService.get_queue_status(queue_id)

        if status is None:
            raise HTTPException(
                status_code=404,
                detail="队列不存在或已过期"
            )

        # 验证用户是否有权限查看该队列
        if str(status.get("user_id")) != str(current_user.username):
            raise HTTPException(
                status_code=403,
                detail="无权访问此队列"
            )

        return status
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel-queue/{queue_id}")
async def cancel_queue(
    queue_id: str,
    current_user: User = Depends(get_current_user)
):
    """取消队列"""
    try:
        success = QueueService.cancel_queue(
            queue_id, str(current_user.username))

        if not success:
            raise HTTPException(
                status_code=404,
                detail="队列不存在或无权取消"
            )

        return {"success": True, "message": "队列已取消"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active-queues", response_model=ActiveQueuesResponse)
async def get_active_queues(
    current_user: User = Depends(get_current_user)
):
    """获取用户的所有活跃队列"""
    try:
        # 获取用户的活跃队列
        active_queues = QueueService.get_user_active_queues(
            current_user.username)
        return {"queues": active_queues}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ... existing code ...
