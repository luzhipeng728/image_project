from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from ..services.image_service import ImageService
from ..services.redis_queue_service import RedisQueueService
from ..models.models import User, Project, Image
from ..core.auth import get_current_user
from pydantic import BaseModel, Field
from ..database.database import get_db
import random
from multiprocessing import Process
import time
import sqlite3

router = APIRouter()

# 任务相关模型
class GenerationTask(BaseModel):
    image_id: int
    image_url: str
    prompt: str
    width: Optional[int] = 1024
    height: Optional[int] = 1024
    seeds: List[int] = Field(default_factory=list)
    source_image_path: str

class TaskResponse(BaseModel):
    task_id: str

class TaskStatus(BaseModel):
    task_id: str
    status: str
    created_at: str
    updated_at: str
    progress: Optional[float] = None
    result: Optional[Dict] = None
    error: Optional[str] = None

class BatchGenerationRequest(BaseModel):
    prompt: str
    model_id: str

class BatchGenerationResponse(BaseModel):
    task_id: str

class BatchTaskStatus(BaseModel):
    task_id: int
    status: str
    total_images: int
    completed_images: int
    created_at: str
    updated_at: str
    error: Optional[str] = None

@router.post("/generate", response_model=TaskResponse)
async def create_generation_task(
    task: GenerationTask,
    current_user: User = Depends(get_current_user)
):
    """创建图片生成任务"""
    try:
        # 初始化Redis队列服务
        queue_service = RedisQueueService()
        
        # 创建任务
        task_id = queue_service.create_task({
            **task.dict(),
            "user_id": current_user.username,
            "type": "image_generation"
        })
        
        return {"task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/task/{task_id}", response_model=TaskStatus)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取任务状态"""
    try:
        # 初始化Redis队列服务
        queue_service = RedisQueueService()
        
        # 获取任务状态
        task_info = queue_service.get_task_status(task_id)
        
        if not task_info:
            raise HTTPException(
                status_code=404,
                detail="任务不存在"
            )
            
        # 验证用户权限
        if task_info.get("user_id") != current_user.username:
            raise HTTPException(
                status_code=403,
                detail="无权访问此任务"
            )
            
        return TaskStatus(
            task_id=task_id,
            status=task_info.get("status", "pending"),
            created_at=task_info.get("created_at", ""),
            updated_at=task_info.get("updated_at", ""),
            progress=task_info.get("progress"),
            result=task_info.get("result"),
            error=task_info.get("error")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks", response_model=List[TaskStatus])
async def get_user_tasks(
    current_user: User = Depends(get_current_user)
):
    """获取用户的所有任务"""
    try:
        # 初始化Redis队列服务
        queue_service = RedisQueueService()
        
        # 获取用户任务列表
        tasks = queue_service.get_user_tasks(current_user.username)
        
        return [
            TaskStatus(
                task_id=task.get("task_id"),
                status=task.get("status", "pending"),
                created_at=task.get("created_at", ""),
                updated_at=task.get("updated_at", ""),
                progress=task.get("progress"),
                result=task.get("result"),
                error=task.get("error")
            )
            for task in tasks
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def process_batch_task(task_id: int, db_path: str):
    """后台处理批量任务的函数"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # 获取任务信息
        cursor.execute("""
            SELECT * FROM batch_tasks WHERE id = ?
        """, (task_id,))
        task = cursor.fetchone()
        
        # 获取所有待处理的子任务
        cursor.execute("""
            SELECT * FROM batch_task_details 
            WHERE batch_task_id = ? AND status = 'pending'
        """, (task_id,))
        details = cursor.fetchall()
        
        for detail in details:
            try:
                # 这里调用您的图片生成服务
                # ... 生成图片的代码 ...
                
                # 更新子任务状态
                cursor.execute("""
                    UPDATE batch_task_details 
                    SET status = 'completed', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (detail['id'],))
                
                # 更新主任务进度
                cursor.execute("""
                    UPDATE batch_tasks 
                    SET completed_images = completed_images + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (task_id,))
                
                conn.commit()
                
            except Exception as e:
                cursor.execute("""
                    UPDATE batch_task_details 
                    SET status = 'failed', error = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (str(e), detail['id']))
                conn.commit()
        
        # 更新任务状态为完成
        cursor.execute("""
            UPDATE batch_tasks 
            SET status = 'completed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (task_id,))
        conn.commit()
        
    except Exception as e:
        cursor.execute("""
            UPDATE batch_tasks 
            SET status = 'failed', error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (str(e), task_id))
        conn.commit()
    finally:
        conn.close()

@router.post("/batch-generate/{project_id}", response_model=BatchTaskStatus)
async def create_batch_generation_task(
    project_id: int,
    request: BatchGenerationRequest,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """创建项目批量生成任务"""
    cursor = db.cursor()
    try:
        # 检查是否存在未完成的任务
        cursor.execute("""
            SELECT id FROM batch_tasks 
            WHERE project_id = ? AND status IN ('pending', 'processing')
        """, (project_id,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="该项目已存在未完成的批量任务")
        
        # 获取项目信息和权限验证
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        project = cursor.fetchone()
        
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
        
        if project['owner_id'] != current_user.username and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="无权访问此项目")

        # 获取项目中的所有未生成的图片
        cursor.execute(
            "SELECT * FROM images WHERE project_id = ? AND is_generated = 0",
            (project_id,)
        )
        images = cursor.fetchall()
        
        if not images:
            raise HTTPException(status_code=400, detail="项目中没有可生成的图片")

        # 创建批量任务
        cursor.execute("""
            INSERT INTO batch_tasks (
                project_id, user_id, total_images, model_id, prompt, status
            ) VALUES (?, ?, ?, ?, ?, 'pending')
            RETURNING id
        """, (project_id, current_user.username, len(images) * 3, 
              request.model_id, request.prompt))
        task_id = cursor.fetchone()[0]
        
        # 创建子任务
        for image in images:
            for _ in range(3):  # 每张图片生成3个版本
                seed = random.randint(1, 999999999)
                cursor.execute("""
                    INSERT INTO batch_task_details (
                        batch_task_id, source_image_id, seed
                    ) VALUES (?, ?, ?)
                """, (task_id, image['id'], seed))
        
        db.commit()
        
        # 启动后台处理进程
        Process(target=process_batch_task, 
                args=(task_id, DATABASE_URL)).start()
        
        return BatchTaskStatus(
            task_id=task_id,
            status="pending",
            total_images=len(images) * 3,
            completed_images=0,
            created_at=time.strftime('%Y-%m-%d %H:%M:%S'),
            updated_at=time.strftime('%Y-%m-%d %H:%M:%S')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/batch-task/{task_id}", response_model=BatchTaskStatus)
async def get_batch_task_status(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """获取批量任务状态"""
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT bt.*, p.owner_id 
            FROM batch_tasks bt
            JOIN projects p ON bt.project_id = p.id
            WHERE bt.id = ?
        """, (task_id,))
        task = cursor.fetchone()
        
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
            
        if task['user_id'] != current_user.username and \
           task['owner_id'] != current_user.username and \
           not current_user.is_admin:
            raise HTTPException(status_code=403, detail="无权访问此任务")
            
        return BatchTaskStatus(
            task_id=task_id,
            status=task['status'],
            total_images=task['total_images'],
            completed_images=task['completed_images'],
            created_at=task['created_at'],
            updated_at=task['updated_at'],
            error=task['error']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

