import asyncio
import logging
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.queue_worker import QueueWorker
from app.services.redis_queue_service import RedisQueueService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def monitor_queues():
    """监控并处理新的队列"""
    redis_service = RedisQueueService()
    worker = QueueWorker()
    
    logger.info("队列处理服务已启动，等待新的队列...")
    
    while True:
        try:
            # 获取所有活跃的队列
            active_queues = redis_service.get_all_active_queues()
            
            # 处理每个等待中的队列
            for queue_info in active_queues:
                queue_id = queue_info["queue_id"]
                status = queue_info.get("status")
                
                # 只处理等待中的队列
                if status == "waiting":
                    logger.info(f"发现新队列: {queue_id}")
                    # 启动队列处理
                    asyncio.create_task(worker.start_queue(queue_id))
            
            # 每秒检查一次新队列
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"监控队列时出错: {str(e)}")
            await asyncio.sleep(5)  # 出错后等待更长时间

async def main():
    try:
        await monitor_queues()
    except KeyboardInterrupt:
        logger.info("正在关闭队列处理服务...")
    except Exception as e:
        logger.error(f"队列处理服务出错: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 