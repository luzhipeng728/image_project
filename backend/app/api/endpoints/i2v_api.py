from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Path, Body
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio
import threading
import os
import uuid
import json
from pydantic import BaseModel
from queue import Queue
import time

# 导入数据库操作
from ...database.database import (
    get_db_context,
    create_i2v_generation,
    get_i2v_generation,
    get_user_i2v_generations,
    update_i2v_generation_status
)

# 导入I2V服务
from .image_to_video import I2VService

# 导入验证token函数
from ...core.auth import verify_token

# 创建路由器
router = APIRouter()

# 存储正在进行的任务
active_tasks = {}

# 创建任务队列
task_queue = Queue()
# 标记是否有正在处理的任务
is_processing = False
# 队列处理锁，用于保护并发访问
queue_lock = threading.Lock()

# 节点ID到状态的映射
NODE_STATUS_MAPPING = {
    "11": "initializing",  # 初始化服务
    "13": "loading_model",  # 加载模型
    "16": "preparing_environment",  # 准备环境
    "17": "setting_parameters",  # 设置迭代参数
    "18": "loading_image",  # 加载图像
    "21": "preprocessing_image",  # 预处理图像
    "22": "configuring_model",  # 配置模型参数
    "23": "preparing_prompt",  # 准备提示词
    "24": "setting_sampler",  # 设置采样器
    "25": "configuring_scheduler",  # 配置调度器
    "26": "preparing_inference",  # 准备推理
    "27": "inference",  # 视频生成推理
    "28": "postprocessing_frames",  # 后处理帧
    "29": "preparing_video",  # 准备视频
    "30": "combining_video",  # 拼接视频
    "31": "optimizing_video",  # 优化视频
    "32": "postprocessing_video",  # 后处理视频
    "40": "completed"  # 完成处理
}

# 节点ID到中文描述的映射
NODE_DESCRIPTIONS = {
    "11": "初始化服务",
    "13": "加载模型",
    "16": "准备环境",
    "17": "设置迭代参数",
    "18": "加载图像",
    "21": "预处理图像",
    "22": "配置模型参数",
    "23": "准备提示词",
    "24": "设置采样器",
    "25": "配置调度器",
    "26": "准备推理",
    "27": "视频生成推理",
    "28": "后处理帧",
    "29": "准备视频",
    "30": "拼接视频",
    "31": "优化视频",
    "32": "后处理视频",
    "40": "完成处理"
}

# 定义请求体模型


class VideoGenerationRequest(BaseModel):
    prompt: str
    image_base64: str
    steps: int = 10
    num_frames: int = 81

# 创建视频生成任务


@router.post("/create")
async def create_video_generation(
    background_tasks: BackgroundTasks,
    request: VideoGenerationRequest,
    username: str = Depends(verify_token)
):
    """
    创建新的图像到视频生成任务

    Args:
        request: 包含所有参数的请求体
        username: 从token中获取的用户名

    Returns:
        包含任务ID的字典
    """
    if not request.image_base64:
        raise HTTPException(
            status_code=400, detail="必须提供image_base64")

    # 处理base64图片数据，保存为临时文件
    temp_image_path = None
    try:
        # 解码base64数据
        import base64
        image_data = base64.b64decode(request.image_base64)

        # 创建临时文件
        temp_dir = "temp_images"
        os.makedirs(temp_dir, exist_ok=True)
        temp_image_path = os.path.join(
            temp_dir, f"{username}_{uuid.uuid4()}.jpg")

        # 保存图片
        with open(temp_image_path, "wb") as f:
            f.write(image_data)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"图片数据处理失败: {str(e)}")

    # 创建数据库记录
    task_id = create_i2v_generation(
        username=username,
        prompt=request.prompt,
        steps=request.steps,
        num_frames=request.num_frames
    )

    # 创建任务对象
    task = {
        "task_id": task_id,
        "image_path": temp_image_path,
        "prompt": request.prompt,
        "steps": request.steps,
        "num_frames": request.num_frames
    }

    global is_processing

    with queue_lock:
        # 检查是否有正在处理的任务
        if is_processing:
            # 如果有正在处理的任务，将当前任务添加到队列
            task_queue.put(task)
            # 更新任务状态为排队中
            update_i2v_generation_status(
                generation_id=task_id,
                status="queued",
                progress=0,
                node_id=None,
                node_status=None,
                node_description=None
            )
            return {"task_id": task_id, "status": "queued"}
        else:
            # 如果没有正在处理的任务，立即处理
            is_processing = True

    # 在后台启动视频生成任务
    background_tasks.add_task(
        process_task_and_check_queue,
        task=task
    )

    return {"task_id": task_id, "status": "initializing", "node_id": "11", "node_description": NODE_DESCRIPTIONS["11"]}

# 处理任务并检查队列的函数


def process_task_and_check_queue(task):
    """
    处理单个任务并检查队列中是否有更多任务

    Args:
        task: 任务对象
    """
    global is_processing

    try:
        # 处理当前任务
        process_video_generation(
            task_id=task["task_id"],
            image_path=task["image_path"],
            prompt=task["prompt"],
            steps=task["steps"],
            num_frames=task["num_frames"]
        )
    finally:
        # 检查队列中是否有更多任务
        with queue_lock:
            if not task_queue.empty():
                # 获取下一个任务
                next_task = task_queue.get()
                # 更新任务状态为处理中
                update_i2v_generation_status(
                    generation_id=next_task["task_id"],
                    status="initializing",
                    progress=0,
                    node_id="11",
                    node_status="initializing",
                    node_description=NODE_DESCRIPTIONS["11"]
                )
                # 处理下一个任务
                threading.Thread(
                    target=process_task_and_check_queue,
                    args=(next_task,)
                ).start()
            else:
                # 如果没有更多任务，重置处理标志
                is_processing = False

# 获取任务状态


@router.get("/status/{task_id}")
async def get_task_status(task_id: int = Path(...)):
    """
    获取视频生成任务的状态

    Args:
        task_id: 任务ID

    Returns:
        包含任务状态的字典
    """
    # 从数据库获取任务信息
    task = get_i2v_generation(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 处理视频路径，添加基础URL前缀
    video_path = task["video_path"]
    if video_path and not video_path.startswith('http'):
        # 移除可能的前导斜杠
        if video_path.startswith('/'):
            video_path = video_path[1:]
        video_path = video_path.replace('mnt/data/lu/ComfyUI/output/', '')
        video_path = f"http://36.213.56.75:9008/{video_path}"

    # 如果任务状态为queued，计算队列位置
    queue_position = None
    if task["status"] == "queued":
        # 计算队列中的位置
        position = 1  # 默认位置为1（队列中的第一个）
        with queue_lock:
            # 遍历队列中的所有任务
            for i in range(task_queue.qsize()):
                queued_task = task_queue.queue[i]
                if queued_task["task_id"] == task_id:
                    queue_position = position
                    break
                position += 1

    response = {
        "task_id": task["id"],
        "status": task["status"],
        "progress": task["progress"],
        "estimated_time": task["estimated_time"],
        "video_path": video_path,
        "error_message": task["error_message"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"]
    }

    # 添加节点相关信息（如果有）
    if hasattr(task, "node_id") and task["node_id"]:
        response["node_id"] = task["node_id"]
        response["node_status"] = task["node_status"] if hasattr(
            task, "node_status") else None
        response["node_description"] = task["node_description"] if hasattr(
            task, "node_description") else None

    # 如果有队列位置信息，添加到响应中
    if queue_position:
        response["queue_position"] = queue_position

    return response

# 获取用户的所有任务


@router.get("/user")
async def get_user_tasks(username: str = Depends(verify_token)):
    """
    获取当前登录用户的所有视频生成任务

    Args:
        username: 从token中获取的用户名

    Returns:
        包含任务列表的字典
    """
    tasks = get_user_i2v_generations(username)

    # 处理每个任务的视频路径，添加基础URL前缀
    for task in tasks:
        video_path = task.get("video_path")
        if video_path and not video_path.startswith('http'):
            # 移除可能的前导斜杠
            if video_path.startswith('/'):
                video_path = video_path[1:]
            video_path = video_path.replace('mnt/data/lu/ComfyUI/output/', '')
            task["video_path"] = f"http://36.213.56.75:9008/{video_path}"

        # 如果任务状态为queued，计算队列位置
        if task["status"] == "queued":
            # 计算队列中的位置
            position = 1  # 默认位置为1（队列中的第一个）
            with queue_lock:
                # 遍历队列中的所有任务
                for i in range(task_queue.qsize()):
                    queued_task = task_queue.queue[i]
                    if queued_task["task_id"] == task["id"]:
                        task["queue_position"] = position
                        break
                    position += 1

    return {"tasks": tasks}

# 添加视频代理接口，解决CORS问题


# @router.get("/video_proxy")
# async def proxy_video(video_url: str = Query(..., description="要代理的视频URL")):
#     """
#     代理视频文件，解决CORS问题

#     Args:
#         video_url: 视频文件的URL

#     Returns:
#         视频文件流
#     """
#     import httpx
#     import re

#     # 验证URL，只接受来自可信源的请求
#     allowed_pattern = r"^http://36\.213\.56\.75:9008/.*\.(mp4|webm|avi|mov)$"
#     if not re.match(allowed_pattern, video_url):
#         raise HTTPException(status_code=400, detail="无效的视频URL")

#     try:
#         async with httpx.AsyncClient() as client:
#             # 流式传输视频内容
#             response = await client.get(video_url, follow_redirects=True)

#             if response.status_code != 200:
#                 raise HTTPException(
#                     status_code=response.status_code, detail="视频获取失败")

#             # 确定内容类型
#             content_type = response.headers.get("content-type", "video/mp4")

#             # 创建一个流式响应
#             return StreamingResponse(
#                 content=response.iter_bytes(),
#                 media_type=content_type,
#                 headers={
#                     "Content-Disposition": f"inline; filename={video_url.split('/')[-1]}"
#                 }
#             )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"代理请求失败: {str(e)}")

# 后台处理视频生成的函数


def process_video_generation(
    task_id: int,
    prompt: str,
    steps: int,
    num_frames: int,
    image_path: str
):
    """
    在后台处理视频生成任务

    Args:
        task_id: 任务ID
        prompt: 提示词
        steps: 生成步数
        num_frames: 帧数
        image_path: 图像路径
    """
    try:
        # 更新任务状态为处理中（初始化）
        update_i2v_generation_status(
            generation_id=task_id,
            status="initializing",
            progress=0,
            node_id="11",
            node_status="initializing",
            node_description=NODE_DESCRIPTIONS["11"]
        )

        # 创建I2V服务实例
        service = I2VService()

        # 检查图像路径
        if not os.path.exists(image_path):
            raise Exception(f"图像不存在: {image_path}")

        # 记录任务到活动任务字典
        active_tasks[task_id] = {
            "service": service,
            "start_time": datetime.now()
        }

        # 处理视频生成事件
        for event in service.generate_video(
            image_path=image_path,
            positive_prompt=prompt,
            steps=steps,
            num_frames=num_frames
        ):
            event_type = event.get("event_type")

            # 获取当前节点信息（如果有）
            node_id = None
            node_status = None
            node_description = None

            # 处理执行中的节点
            if event_type == "executing" and "data" in event and "node" in event["data"]:
                node_id = event["data"]["node"]
                node_status = NODE_STATUS_MAPPING.get(node_id, "processing")
                node_description = NODE_DESCRIPTIONS.get(node_id, "")

            # 处理进度事件
            if event_type == "progress":
                data = event.get("data", {})
                # 从状态中获取进度信息
                status = event.get("status", {})

                # 获取推理进度或视频拼接进度
                inference_progress = status.get("inference_progress", 0)
                video_progress = status.get("video_progress", 0)

                # 计算总体进度（推理占70%，视频拼接占30%）
                if status.get("video_combine", False):
                    # 如果已经到了视频拼接阶段
                    total_progress = int(70 + (video_progress * 0.3))
                    # 更新节点信息
                    node_id = "30"  # 拼接视频阶段
                    node_status = "combining_video"
                    node_description = NODE_DESCRIPTIONS["30"]
                else:
                    # 如果还在推理阶段
                    total_progress = int(inference_progress * 0.7)
                    # 更新节点信息（如果之前没有设置）
                    if not node_id:
                        node_id = "27"  # 视频生成推理
                        node_status = "inference"
                        node_description = NODE_DESCRIPTIONS["27"]

                # 获取预估剩余时间
                time_estimate = status.get("total_time_estimate", {})
                estimated_time = time_estimate.get(
                    "estimated_remaining_seconds", 0)

                # 更新数据库中的任务状态
                update_i2v_generation_status(
                    generation_id=task_id,
                    status=node_status or "processing",
                    progress=total_progress,
                    estimated_time=estimated_time,
                    node_id=node_id,
                    node_status=node_status,
                    node_description=node_description
                )

            elif event_type == "complete":
                data = event.get("data", {})
                video_path = data.get("video_path")

                # 确保视频路径存在
                if not video_path:
                    # 尝试从状态中获取视频路径
                    status = event.get("status", {})
                    video_path = status.get("video_path")

                # 更新数据库中的任务状态
                update_i2v_generation_status(
                    generation_id=task_id,
                    status="completed",
                    progress=100,
                    estimated_time=0,
                    video_path=video_path,
                    node_id="40",
                    node_status="completed",
                    node_description=NODE_DESCRIPTIONS["40"]
                )

            elif event_type == "error":
                data = event.get("data", {})
                error_message = data.get("message", "未知错误")

                # 更新数据库中的任务状态
                update_i2v_generation_status(
                    generation_id=task_id,
                    status="failed",
                    error_message=error_message,
                    node_id=node_id,
                    node_status="error",
                    node_description=node_description
                )

        # 从活动任务字典中移除任务
        if task_id in active_tasks:
            del active_tasks[task_id]

    except Exception as e:
        # 处理异常
        error_message = str(e)
        print(f"视频生成任务 {task_id} 失败: {error_message}")

        # 更新数据库中的任务状态
        update_i2v_generation_status(
            generation_id=task_id,
            status="failed",
            error_message=error_message
        )

        # 从活动任务字典中移除任务
        if task_id in active_tasks:
            del active_tasks[task_id]
