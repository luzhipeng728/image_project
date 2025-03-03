import asyncio
import logging
import json
from typing import Dict, Any
from .redis_queue_service import RedisQueueService
from .image_service import ImageService

logger = logging.getLogger(__name__)

class BatchGenerationWorker:
    def __init__(self):
        self.redis_service = RedisQueueService()
        self.stop_event = asyncio.Event()

    async def process_single_image(self, task_data: Dict[str, Any], image_data: Dict[str, Any]) -> None:
        """处理单张图片的生成任务"""
        image_id = None
        try:
            # 获取图片信息
            image_id = image_data["image_id"]
            image_path = image_data["image_path"]
            seeds = image_data["seeds"]

            # 为每个seed生成一张图片
            for seed in seeds:
                try:
                    # 调用图生图API
                    await ImageService.generate_image(
                        username=task_data["user_id"],
                        prompt=task_data["prompt"],
                        model_id=task_data["model_id"],
                        seed=seed,
                        source_image_id=image_id,
                        generation_type='image_to_image',
                        project_id=task_data["project_id"]
                    )

                    # 更新已完成数量
                    task_data["completed_images"] = task_data.get("completed_images", 0) + 1
                    progress = (task_data["completed_images"] / task_data["total_images"]) * 100
                    
                    # 更新任务状态
                    self.redis_service.update_task_status(
                        task_data["task_id"],
                        "processing",
                        {"progress": progress}
                    )

                except Exception as e:
                    logger.error(f"生成图片失败 (image_id: {image_id}, seed: {seed}): {str(e)}")
                    # 继续处理下一个seed，不中断整个任务

        except Exception as e:
            error_msg = f"处理图片失败 (image_id: {image_id if image_id else 'unknown'}): {str(e)}"
            logger.error(error_msg)
            # 更新任务状态为失败
            self.redis_service.update_task_status(
                task_data["task_id"],
                "failed",
                {
                    "error": error_msg,
                    "progress": 0
                }
            )

    async def process_batch_task(self, task_data: Dict[str, Any]) -> None:
        """处理批量生成任务"""
        try:
            # 更新任务状态为处理中
            self.redis_service.update_task_status(
                task_data["task_id"],
                "processing",
                {"progress": 0}
            )

            # 并发处理所有图片
            tasks = []
            for image_data in task_data["images"]:
                task = asyncio.create_task(
                    self.process_single_image(task_data, image_data)
                )
                tasks.append(task)

            # 等待所有任务完成
            await asyncio.gather(*tasks)

            # 更新任务状态为完成
            self.redis_service.update_task_status(
                task_data["task_id"],
                "completed",
                {"progress": 100}
            )

        except Exception as e:
            logger.error(f"处理批量生成任务失败: {str(e)}")
            # 更新任务状态为失败
            self.redis_service.update_task_status(
                task_data["task_id"],
                "failed",
                {"error": str(e)}
            )

    async def run(self):
        """运行工作进程"""
        logger.info("批量生成工作进程启动")

        while not self.stop_event.is_set():
            try:
                # 获取下一个任务
                task_id = self.redis_service.get_next_task()
                
                if task_id:
                    # 获取任务信息
                    task_data = self.redis_service.get_task_status(task_id)
                    
                    if task_data and task_data.get("type") == "batch_generation":
                        # 处理批量生成任务
                        await self.process_batch_task(task_data)
                    
                await asyncio.sleep(1)  # 避免过于频繁的轮询
                
            except Exception as e:
                logger.error(f"处理任务时发生错误: {str(e)}")
                await asyncio.sleep(5)  # 发生错误时等待更长时间

    def stop(self):
        """停止工作进程"""
        self.stop_event.set() 