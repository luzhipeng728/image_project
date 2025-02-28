import os
import json
import logging
import time
import asyncio
import redis
from typing import Dict, List, Any, Optional
import traceback

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis连接
_redis_conn = None


def get_redis_connection():
    """获取Redis连接"""
    global _redis_conn
    if _redis_conn is None:
        try:
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", 6379))
            db = int(os.getenv("REDIS_DB", 0))

            _redis_conn = redis.Redis(
                host=host,
                port=port,
                db=db
            )
        except Exception as e:
            logger.error(f"连接Redis失败: {e}")
            raise
    return _redis_conn


def update_task_progress(task_id, progress, status="processing"):
    """更新任务进度

    Args:
        task_id: 任务ID
        progress: 进度百分比 (0-100)
        status: 任务状态 (processing, completed, failed)
    """
    try:
        redis_conn = get_redis_connection()
        progress_key = f"task_progress:{task_id}"

        # 更新进度和状态
        redis_conn.hset(progress_key, "progress", progress)
        redis_conn.hset(progress_key, "status", status)

        # 设置过期时间 (1小时)
        redis_conn.expire(progress_key, 3600)

        logger.debug(f"更新任务进度: {task_id}, 进度: {progress}%, 状态: {status}")
    except Exception as e:
        logger.error(f"更新任务进度失败: {e}")


def process_image_task(task_data: Dict) -> bool:
    """
    处理图像生成任务

    Args:
        task_data: 任务数据，包括image_id, image_url, prompt等

    Returns:
        success: 是否成功完成任务
    """
    # 记录任务开始
    queue_id = task_data.get("queue_id")
    image_id = task_data.get("image_id")
    job_id = task_data.get("job_id")  # 获取job_id用于进度更新

    logger.info(
        f"开始处理任务: queue_id={queue_id}, image_id={image_id}, job_id={job_id}")

    # 初始化进度为0
    if job_id:
        update_task_progress(job_id, 0)

    try:
        # 导入所需服务，避免循环导入
        from ..image_service import ImageService
        from ..queue.queue_service import QueueService

        # 获取任务参数
        image_url = task_data.get("image_url")
        prompt = task_data.get("prompt", "")
        model_id = task_data.get("model_id")
        project_id = task_data.get("project_id")

        # 可选参数
        seed = task_data.get("seed")
        width = task_data.get("width")
        height = task_data.get("height")
        enhance = task_data.get("enhance", False)
        username = task_data.get("username", "admin")

        # 验证必要参数
        if not image_url:
            raise ValueError("缺少必要参数: image_url")
        if not model_id:
            raise ValueError("缺少必要参数: model_id")
        if not project_id:
            raise ValueError("缺少必要参数: project_id")

        # 创建存储结果的列表
        results = []

        # 创建一个共享的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 创建并行任务列表
        tasks = []

        # 更新进度为10%（开始并行处理）
        if job_id:
            update_task_progress(job_id, 10)

        # 生成三种变体图像并创建异步任务
        for variant_idx in range(3):
            # 生成不同的种子以创建变体
            variant_seed = seed + variant_idx if seed is not None else None
            variant_prompt = f"{prompt} (variant {variant_idx+1})" if prompt else f"variant {variant_idx+1}"

            # 创建异步任务
            tasks.append(
                ImageService.generate_image_to_image(
                    image_url=image_url,
                    prompt=variant_prompt,
                    model_id=model_id,
                    project_id=project_id,
                    seed=variant_seed,
                    width=width,
                    height=height,
                    enhance=enhance,
                    username=username
                )
            )

            logger.info(
                f"已创建变体 {variant_idx+1}/3 生成任务: queue_id={queue_id}, image_id={image_id}")

        # 并行执行所有任务并等待结果
        try:
            # 使用gather并行执行所有任务
            variant_results = loop.run_until_complete(
                asyncio.gather(*tasks, return_exceptions=True))

            # 处理结果
            for variant_idx, result in enumerate(variant_results):
                if isinstance(result, Exception):
                    # 处理异常情况
                    error_msg = f"生成变体 {variant_idx+1}/3 失败: {str(result)}"
                    logger.error(f"{error_msg}\n{traceback.format_exc()}")
                    # 不中断处理，继续下一个
                else:
                    # 添加变体索引到结果
                    result["variant_index"] = variant_idx
                    results.append(result)
                    logger.info(
                        f"变体 {variant_idx+1}/3 生成成功: {result.get('url', '无URL')}")

                # 更新进度 - 每个变体占30%，从10%开始，最多90%
                if job_id:
                    progress = min(10 + (variant_idx + 1) * 30, 90)
                    update_task_progress(job_id, progress)
        except Exception as e:
            error_msg = f"并行处理变体失败: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")

        # 关闭事件循环
        loop.close()

        # 检查是否至少生成了一个变体
        if not results:
            if job_id:
                update_task_progress(job_id, 100, "failed")
            raise ValueError("所有变体生成均失败")

        # 更新进度为100%，状态为completed
        if job_id:
            update_task_progress(job_id, 100, "completed")

        # 报告任务成功
        success = QueueService.report_task_success(
            queue_id, task_data, results)

        if success:
            logger.info(
                f"任务完成: queue_id={queue_id}, image_id={image_id}, 生成了 {len(results)} 个变体")
        else:
            logger.warning(
                f"任务完成但报告失败: queue_id={queue_id}, image_id={image_id}")

        return success

    except Exception as e:
        # 记录错误
        error_msg = f"处理任务失败: {str(e)}"
        stack_trace = traceback.format_exc()
        logger.error(f"{error_msg}\n{stack_trace}")

        # 更新进度状态为失败
        if job_id:
            update_task_progress(job_id, 100, "failed")

        try:
            # 导入队列服务来报告失败
            from ..queue.queue_service import QueueService
            # 报告任务失败
            QueueService.report_task_failure(queue_id, task_data, error_msg)

        except Exception as report_error:
            logger.error(f"报告任务失败时出错: {report_error}")

        return False


def start_worker(queues=None, num_workers=1):
    """
    启动工作进程

    Args:
        queues: 要监听的队列列表，None表示监听所有队列
        num_workers: 工作进程数量
    """
    # 导入所需模块，避免循环导入
    from rq import Worker, Queue
    from ..queue.queue_service import QueueService

    # 获取Redis连接
    redis_conn = QueueService.get_redis_connection()

    # 如果没有指定队列，则创建默认队列
    if not queues:
        queues = [Queue('default', connection=redis_conn)]

    logger.info(f"启动 {num_workers} 个工作进程来监听队列")

    # 启动Worker - 不使用Connection上下文管理器
    # 直接创建Worker并启动
    worker = Worker(queues, connection=redis_conn)
    worker.work()  # 不使用 name 参数
