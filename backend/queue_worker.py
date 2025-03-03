#!/usr/bin/env python
"""
图像生成队列工作进程
这个脚本作为独立进程运行，负责监控Redis中的新队列并处理任务
使用方法:
    python queue_worker.py --concurrency=3
"""

import os
import sys
import argparse
import logging
import time
import signal
import asyncio
from datetime import datetime

# 添加应用程序路径到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入应用服务
from app.services.redis_queue_service import RedisQueueService
from app.services.image_service import ImageService

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("queue_worker.log")
    ]
)
logger = logging.getLogger("queue_worker")

# 全局变量
stop_event = asyncio.Event()
redis_service = None

async def process_task(task_data):
    """处理单个任务"""
    task_id = task_data.get("task_id", "unknown")
    queue_id = task_data.get("queue_id", "unknown")
    
    try:
        logger.info(f"开始处理任务 {task_id} (队列 {queue_id})")
        
        # 更新任务状态为处理中
        redis_service.update_task_status(task_id, "processing")

        # 调用图像生成服务
        logger.info(f"开始生成图像: prompt='{task_data.get('prompt', '')}'")
        result = await ImageService.generate_image_from_task(task_data)
        logger.info(f"图像生成完成: {len(result.get('variants', []))} 个变体")

        # 更新任务状态为完成
        redis_service.update_task_status(
            task_id, 
            "completed",
            result
        )
        logger.info(f"任务 {task_id} 处理完成")
        return True

    except Exception as e:
        logger.error(f"任务 {task_id} 处理失败: {str(e)}", exc_info=True)
        try:
            redis_service.update_task_status(
                task_id,
                "failed",
                {"error": str(e)}
            )
        except Exception as update_error:
            logger.error(f"更新任务 {task_id} 状态失败: {str(update_error)}")
        return False

async def process_queue(queue_id, concurrency):
    """处理指定队列中的任务"""
    try:
        # 获取队列信息
        queue_info = redis_service.get_queue_status(queue_id)
        if not queue_info:
            logger.error(f"队列 {queue_id} 不存在或已过期")
            return
            
        # 获取并验证队列参数
        concurrency = int(queue_info.get("concurrency", concurrency))
        total_tasks = int(queue_info.get("total_tasks", 0))
        
        if total_tasks == 0:
            logger.warning(f"队列 {queue_id} 没有任务需要处理")
            redis_service.update_queue_status(queue_id, "completed")
            return
            
        logger.info(f"开始处理队列 {queue_id}, 并发数: {concurrency}, 总任务数: {total_tasks}")
        
        # 更新队列状态为处理中
        redis_service.update_queue_status(queue_id, "processing")
        
        # 处理队列中的任务
        tasks = set()
        while not stop_event.is_set():
            # 如果当前运行的任务数小于并发数，尝试获取新任务
            while len(tasks) < concurrency and not stop_event.is_set():
                task_data = redis_service.get_next_task(queue_id)
                if not task_data:
                    break  # 队列为空
                
                # 创建新的任务
                task = asyncio.create_task(process_task(task_data))
                tasks.add(task)
            
            if not tasks:
                # 如果没有正在运行的任务，检查队列是否已完成
                queue_info = redis_service.get_queue_status(queue_id)
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
            
        # 再次检查队列状态，确认是否所有任务都已完成
        final_status = redis_service.get_queue_status(queue_id)
        if final_status:
            completed = int(final_status.get("completed_tasks", 0))
            failed = int(final_status.get("failed_tasks", 0))
            total = int(final_status.get("total_tasks", 0))
            
            logger.info(f"队列 {queue_id} 处理完成: 总任务数={total}, 完成={completed}, 失败={failed}")
            
            # 如果所有任务都已完成，更新队列状态
            if completed + failed >= total:
                logger.info(f"队列 {queue_id} 所有任务已处理完成，更新状态为completed")
                redis_service.update_queue_status(queue_id, "completed")
            else:
                # 如果还有未完成的任务，重新计算状态
                current_status = redis_service._calculate_queue_status(queue_id, total, completed, failed)
                logger.info(f"队列 {queue_id} 还有未完成任务，更新状态为 {current_status}")
                redis_service.update_queue_status(queue_id, current_status)
                
    except Exception as e:
        logger.error(f"处理队列 {queue_id} 时发生错误: {str(e)}")
        # 更新队列状态为失败
        try:
            redis_service.update_queue_status(queue_id, "failed")
        except:
            pass

async def monitor_new_queues(concurrency):
    """监控新队列触发标记"""
    global redis_service
    
    logger.info("开始监控新队列...")
    
    while not stop_event.is_set():
        try:
            # 查找新队列触发标记
            trigger_keys = redis_service.redis.keys("worker:trigger:new_queue:*")
            
            for key in trigger_keys:
                try:
                    # 从键中提取队列ID - 修复解码问题
                    queue_id = key.split(':')[-1] if isinstance(key, str) else key.decode('utf-8').split(':')[-1]
                    
                    # 删除触发标记
                    redis_service.redis.delete(key)
                    
                    # 启动队列处理
                    logger.info(f"发现新队列: {queue_id}")
                    asyncio.create_task(process_queue(queue_id, concurrency))
                    
                except Exception as e:
                    logger.error(f"处理队列触发标记失败: {e}")
            
            # 检查活跃队列
            active_queues = redis_service.get_all_active_queues()
            for queue in active_queues:
                queue_id = queue.get("queue_id")
                status = queue.get("status")
                
                # 如果队列状态为waiting，启动处理
                if status == "waiting":
                    logger.info(f"发现等待中的队列: {queue_id}")
                    asyncio.create_task(process_queue(queue_id, concurrency))
            
            # 每5秒检查一次
            await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"监控新队列时发生错误: {e}")
            await asyncio.sleep(10)  # 发生错误后等待时间更长

def signal_handler():
    """信号处理函数"""
    logger.info("收到停止信号，准备关闭...")
    stop_event.set()

async def main():
    """主函数"""
    global redis_service
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="图像生成队列工作进程")
    parser.add_argument("--concurrency", type=int, default=3, help="并发处理任务数")
    args = parser.parse_args()
    
    # 初始化Redis队列服务
    redis_service = RedisQueueService()
    
    # 设置信号处理
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
    
    logger.info(f"队列工作进程启动，并发数: {args.concurrency}")
    
    # 启动监控
    try:
        await monitor_new_queues(args.concurrency)
    except asyncio.CancelledError:
        logger.info("工作进程被取消")
    finally:
        logger.info("工作进程关闭")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("收到键盘中断，退出程序")
    except Exception as e:
        logger.error(f"程序异常退出: {e}", exc_info=True) 