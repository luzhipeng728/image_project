from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from ..services.image_service import ImageService
from ..models.models import User
from ..core.auth import get_current_user

router = APIRouter()

@router.get("/history")
async def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    generation_type: Optional[str] = Query(None, regex="^(text_to_image|image_to_image)$"),
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

# ... existing code ... 