import asyncio
import logging
from typing import Optional, Dict
from .redis_queue_service import RedisQueueService
from .image_service import ImageService
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QueueWorker:
    def __init__(self):
        self.redis_service = RedisQueueService()
        self.running_tasks = {}
        self.stop_event = asyncio.Event()

    async def process_task(self, task_data: Dict):
        """处理单个任务"""
        task_id = task_data.get("task_id", "unknown")
        queue_id = task_data.get("queue_id", "unknown")
        
        try:
            logger.info(f"开始处理任务 {task_id} (队列 {queue_id})")
            logger.debug(f"任务数据: {task_data}")

            # 更新任务状态为处理中
            self.redis_service.update_task_status(task_id, "processing")

            # 调用图像生成服务
            logger.info(f"开始生成图像: prompt='{task_data.get('prompt', '')}'")
            result = await ImageService.generate_image_from_task(task_data)
            logger.info(f"图像生成完成: {len(result.get('variants', []))} 个变体")

            # 更新任务状态为完成，包含所有变体的结果
            self.redis_service.update_task_status(
                task_id, 
                "completed",
                result
            )
            logger.info(f"任务 {task_id} 处理完成")

        except Exception as e:
            logger.error(f"任务 {task_id} 处理失败: {str(e)}", exc_info=True)
            try:
                self.redis_service.update_task_status(
                    task_id,
                    "failed",
                    {"error": str(e)}
                )
            except Exception as update_error:
                logger.error(f"更新任务 {task_id} 状态失败: {str(update_error)}")
            
            # 重新抛出异常，让上层处理
            raise

    async def process_queue(self, queue_id: str, concurrency: int):
        """处理指定队列中的任务"""
        tasks = set()
        while not self.stop_event.is_set():
            # 如果当前运行的任务数小于并发数，尝试获取新任务
            while len(tasks) < concurrency:
                task_data = self.redis_service.get_next_task(queue_id)
                if not task_data:
                    break  # 队列为空
                
                # 创建新的任务
                task = asyncio.create_task(self.process_task(task_data))
                tasks.add(task)
            
            if not tasks:
                # 如果没有正在运行的任务，检查队列是否已完成
                queue_info = self.redis_service.get_queue_status(queue_id)
                if not queue_info or queue_info.get("status") in ["completed", "cancelled"]:
                    break
                await asyncio.sleep(1)
                continue

            # 等待任意一个任务完成
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 处理完成的任务
            for task in done:
                try:
                    await task
                except Exception as e:
                    logger.error(f"任务执行出错: {str(e)}")
                tasks.remove(task)

        # 等待所有剩余任务完成
        if tasks:
            await asyncio.wait(tasks)

    async def start_queue(self, queue_id: str):
        """开始处理队列中的任务"""
        try:
            # 获取队列信息
            queue_info = self.redis_service.get_queue_status(queue_id)
            if not queue_info:
                logging.error(f"队列 {queue_id} 不存在或已过期")
                return
                
            # 获取并验证队列参数
            concurrency = int(queue_info.get("concurrency", 5))
            total_tasks = int(queue_info.get("total_tasks", 0))
            
            if total_tasks == 0:
                logging.warning(f"队列 {queue_id} 没有任务需要处理")
                self.redis_service.update_queue_status(queue_id, "completed")
                return
                
            logging.info(f"开始处理队列 {queue_id}, 并发数: {concurrency}, 总任务数: {total_tasks}")
            
            # 更新队列状态为处理中
            self.redis_service.update_queue_status(queue_id, "processing")
            
            # 处理队列任务
            await self.process_queue(queue_id, concurrency)
            
            # 再次检查队列状态，确认是否所有任务都已完成
            final_status = self.redis_service.get_queue_status(queue_id)
            if final_status:
                completed = int(final_status.get("completed_tasks", 0))
                failed = int(final_status.get("failed_tasks", 0))
                total = int(final_status.get("total_tasks", 0))
                
                logging.info(f"队列 {queue_id} 处理完成: 总任务数={total}, 完成={completed}, 失败={failed}")
                
                # 如果所有任务都已完成，更新队列状态
                if completed + failed >= total:
                    logging.info(f"队列 {queue_id} 所有任务已处理完成，更新状态为completed")
                    self.redis_service.update_queue_status(queue_id, "completed")
                else:
                    # 如果还有未完成的任务，重新计算状态
                    current_status = self.redis_service._calculate_queue_status(queue_id, total, completed, failed)
                    logging.info(f"队列 {queue_id} 还有未完成任务，更新状态为 {current_status}")
                    self.redis_service.update_queue_status(queue_id, current_status)
                
        except Exception as e:
            logging.error(f"处理队列 {queue_id} 时发生错误: {str(e)}")
            # 更新队列状态为失败
            try:
                self.redis_service.update_queue_status(queue_id, "failed")
            except:
                pass

    def stop(self):
        """停止队列处理"""
        self.stop_event.set() 