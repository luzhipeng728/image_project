#!/usr/bin/env python
"""
图像生成队列工作进程，用于处理后台队列中的图像生成任务。
使用RQ（Redis Queue）作为任务队列基础设施，Redis作为后端存储。

使用方法:
    python worker.py --concurrency=3

参数:
    --concurrency: 并发工作进程数量，默认为1
"""

import os
import sys
import argparse
import logging
import time
import multiprocessing
import signal
import uuid
import threading
from rq import Worker, Queue
import redis
import socket
import json

# 设置环境变量解决 MacOS fork() 问题
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

# 添加应用程序路径到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("worker.log")
    ]
)
logger = logging.getLogger("worker")

# 全局变量
REDIS_CONN = None
WORKER_PROCESSES = []
MONITOR_THREAD = None
SHUTDOWN_EVENT = threading.Event()


def get_redis_connection():
    """获取Redis连接"""
    try:
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", 6379))
        db = int(os.getenv("REDIS_DB", 0))

        return redis.Redis(
            host=host,
            port=port,
            db=db
        )
    except Exception as e:
        logger.error(f"连接Redis失败: {e}")
        sys.exit(1)


def discover_image_generation_queues(redis_conn):
    """发现所有图像生成队列

    此函数使用多种方式查找可能的图像生成队列

    Returns:
        set: 队列名称集合
    """
    queue_names = set()

    # 1. 直接查找以 image_generation_ 开头的键
    for pattern in ["image_generation_*", "rq:queue:image_generation_*"]:
        for key in redis_conn.scan_iter(pattern):
            try:
                key_str = key.decode('utf-8')
                # 如果是 rq:queue: 前缀，去掉前缀
                if key_str.startswith("rq:queue:"):
                    qname = key_str.split(':', 2)[-1]
                else:
                    qname = key_str

                # 确保队列名称以 image_generation_ 开头
                if qname.startswith("image_generation_"):
                    queue_names.add(qname)
                    # logger.debug(f"发现队列: {qname} (来自键: {key_str})")
            except Exception as e:
                logger.error(f"处理队列键 {key} 失败: {e}")

    # 2. 查找所有 rq:queues 集合中的队列
    try:
        queue_set_members = redis_conn.smembers("rq:queues")
        for member in queue_set_members:
            queue_name = member.decode('utf-8')
            if queue_name.startswith("image_generation_"):
                queue_names.add(queue_name)
                # logger.debug(f"从 rq:queues 集合发现队列: {queue_name}")
    except Exception as e:
        logger.error(f"从 rq:queues 集合查找队列失败: {e}")

    # 3. 查找队列触发标记
    try:
        trigger_keys = list(redis_conn.scan_iter(
            "worker:listen:image_generation_*"))
        for key in trigger_keys:
            try:
                key_str = key.decode('utf-8')
                queue_id = key_str.split(':', 2)[-1]
                queue_names.add(queue_id)
                # logger.debug(f"从触发标记发现队列: {queue_id}")
            except Exception as e:
                logger.error(f"处理触发标记 {key} 失败: {e}")
    except Exception as e:
        logger.error(f"查找队列触发标记失败: {e}")

    # 添加特定队列名称，防止被漏掉
    for key in redis_conn.scan_iter("queue:image_generation_*:info"):
        try:
            key_str = key.decode('utf-8')
            parts = key_str.split(':')
            if len(parts) >= 3:
                queue_id = parts[1]
                queue_names.add(queue_id)
                # logger.debug(f"从队列信息键发现队列: {queue_id}")
        except Exception as e:
            logger.error(f"处理队列信息键 {key} 失败: {e}")

    return queue_names


def worker_process(queue_names, worker_id):
    """工作进程函数，在单独的进程中运行

    Args:
        queue_names: 队列名称列表
        worker_id: 工作进程ID
    """
    try:
        # 在子进程中重新初始化Redis连接
        redis_conn = get_redis_connection()

        # 创建RQ队列
        queues = [Queue(name=qname, connection=redis_conn)
                  for qname in queue_names]

        logger.info(
            f"工作进程 {worker_id} (PID: {os.getpid()}) 开始监听 {len(queues)} 个队列")

        # 创建worker并开始工作
        worker = Worker(
            queues,
            connection=redis_conn,
            name=f"{socket.gethostname()}:{worker_id}",
            # 禁用调度器，避免在线程中创建守护进程的问题
            disable_default_exception_handler=True
        )

        # 设置信号处理器
        def handle_shutdown(signum, frame):
            logger.info(f"工作进程 {worker_id} 收到信号 {signum}，准备关闭...")
            worker.request_stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        # 开始工作（此调用是阻塞的）
        worker.work(with_scheduler=False)  # 禁用内置调度器

    except Exception as e:
        logger.error(f"工作进程 {worker_id} (PID: {os.getpid()}) 出错: {e}")
        sys.exit(1)


def update_progress_status():
    """后台线程：更新任务进度状态"""
    redis_conn = get_redis_connection()

    while not SHUTDOWN_EVENT.is_set():
        try:
            # 查找所有图像生成队列信息
            for key in redis_conn.scan_iter("queue:image_generation_*:info"):
                try:
                    key_str = key.decode('utf-8')
                    queue_data_str = redis_conn.get(key_str)

                    if queue_data_str:
                        queue_data = json.loads(queue_data_str)
                        queue_id = key_str.split(':')[1]

                        # 只更新状态为 processing 的队列
                        if queue_data.get('status') == 'processing':
                            # 获取已完成和失败的任务数
                            completed_tasks_key = f"queue:{queue_id}:completed_tasks"
                            failed_tasks_key = f"queue:{queue_id}:failed_tasks"

                            completed_count = len(
                                redis_conn.smembers(completed_tasks_key))
                            failed_count = len(
                                redis_conn.smembers(failed_tasks_key))

                            # 更新队列数据
                            if completed_count != queue_data.get('total_completed', 0) or failed_count != queue_data.get('total_failed', 0):
                                queue_data['total_completed'] = completed_count
                                queue_data['total_failed'] = failed_count

                                # 检查是否所有任务都已处理完成
                                total_tasks = queue_data.get('total_tasks', 0)
                                if completed_count + failed_count >= total_tasks:
                                    queue_data['status'] = 'completed'

                                # 保存回Redis
                                redis_conn.set(key_str, json.dumps(queue_data))
                                logger.info(
                                    f"更新队列进度: {queue_id}, 已完成: {completed_count}, 失败: {failed_count}")
                except Exception as e:
                    logger.error(f"更新队列进度状态失败: {e}")

            # 每5秒检查一次
            time.sleep(5)
        except Exception as e:
            logger.error(f"进度更新线程错误: {e}")
            time.sleep(10)  # 发生错误后等待时间更长


def start_workers(queue_names, concurrency):
    """启动指定数量的工作进程

    Args:
        queue_names: 队列名称列表
        concurrency: 并发工作进程数量

    Returns:
        list: 启动的进程列表
    """
    global WORKER_PROCESSES

    # 清理现有进程
    for p in WORKER_PROCESSES:
        if p.is_alive():
            p.terminate()
            p.join(1)  # 等待最多1秒

    WORKER_PROCESSES = []

    # 启动新进程
    for i in range(concurrency):
        worker_id = f"worker-{i+1}-{uuid.uuid4().hex[:8]}"

        p = multiprocessing.Process(
            target=worker_process,
            args=(queue_names, worker_id),
            daemon=True
        )

        p.start()
        WORKER_PROCESSES.append(p)
        logger.info(f"已启动工作进程 {worker_id} (PID: {p.pid})")

    return WORKER_PROCESSES


def monitor_queues(concurrency):
    """监控队列变化，发现新队列时重启工作进程

    Args:
        concurrency: 工作进程数量
    """
    global REDIS_CONN, SHUTDOWN_EVENT

    # 记录已知队列
    known_queues = set()

    while not SHUTDOWN_EVENT.is_set():
        try:
            # 获取当前所有队列
            current_queues = discover_image_generation_queues(REDIS_CONN)

            # 如果没有队列，添加默认队列
            if not current_queues:
                current_queues = {"default", "image_generation_default"}

                # 确保默认队列存在
                key = "rq:queue:image_generation_default"
                if not REDIS_CONN.exists(key):
                    try:
                        REDIS_CONN.sadd(
                            "rq:queues", "image_generation_default")
                        REDIS_CONN.expire(key, 86400)  # 1天过期
                        logger.info("创建了默认图像生成队列: image_generation_default")
                    except Exception as e:
                        logger.error(f"创建默认队列失败: {e}")

            # 检查是否有新队列或删除队列
            if current_queues != known_queues:
                new_queues = current_queues - known_queues
                removed_queues = known_queues - current_queues

                if new_queues:
                    logger.info(
                        f"发现 {len(new_queues)} 个新队列: {', '.join(new_queues)}")

                if removed_queues:
                    logger.info(
                        f"有 {len(removed_queues)} 个队列已移除: {', '.join(removed_queues)}")

                # 清理Redis中可能存在的旧worker注册信息
                host_id = socket.gethostname()
                worker_keys = REDIS_CONN.keys(f"rq:worker:{host_id}:*")
                if worker_keys:
                    logger.info(f"清理 {len(worker_keys)} 个旧worker注册信息")
                    for key in worker_keys:
                        REDIS_CONN.delete(key)

                # 重启所有工作进程
                logger.info(f"队列发生变化，重启所有工作进程以监听 {len(current_queues)} 个队列")
                start_workers(current_queues, concurrency)

                # 更新已知队列
                known_queues = current_queues

            # 检查工作进程是否健康
            for i, p in enumerate(WORKER_PROCESSES):
                if not p.is_alive():
                    logger.warning(f"工作进程 {i+1} (PID: {p.pid}) 已停止，重启中...")

                    # 创建新进程替换死亡进程
                    worker_id = f"worker-{i+1}-{uuid.uuid4().hex[:8]}"
                    new_p = multiprocessing.Process(
                        target=worker_process,
                        args=(known_queues, worker_id),
                        daemon=True
                    )
                    new_p.start()

                    # 替换进程列表中的元素
                    WORKER_PROCESSES[i] = new_p
                    logger.info(f"已重启工作进程 {worker_id} (PID: {new_p.pid})")

            # 等待10秒再检查
            time.sleep(10)

        except KeyboardInterrupt:
            logger.info("收到中断信号，停止监控")
            break

        except Exception as e:
            logger.error(f"监控队列时出错: {e}")
            time.sleep(5)  # 出错后短暂等待再继续


def signal_handler(signum, frame):
    """主进程的信号处理函数"""
    logger.info(f"收到信号 {signum}，关闭所有工作进程...")

    # 设置关闭事件
    global SHUTDOWN_EVENT
    SHUTDOWN_EVENT.set()

    # 终止所有子进程
    for p in WORKER_PROCESSES:
        if p.is_alive():
            p.terminate()

    # 等待子进程结束
    for p in WORKER_PROCESSES:
        p.join(2)

    # 等待监控线程结束
    if MONITOR_THREAD and MONITOR_THREAD.is_alive():
        MONITOR_THREAD.join(2)

    sys.exit(0)


def main():
    """主函数，解析命令行参数并启动工作进程"""
    global REDIS_CONN, MONITOR_THREAD

    # 设置信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description="图像生成队列工作进程")
    parser.add_argument("--concurrency", type=int, default=5, help="并发工作进程数量")
    args = parser.parse_args()

    concurrency = args.concurrency
    logger.info(f"启动队列监控系统，并发工作进程数: {concurrency}")

    try:
        # 连接Redis
        REDIS_CONN = get_redis_connection()

        # 导入队列服务
        from app.services.queue.queue_service import QueueService

        # 在启动工作进程前，将未完成的队列标记为失败
        updated_count = QueueService.mark_unfinished_queues_as_failed()
        if updated_count > 0:
            logger.info(f"标记了 {updated_count} 个未完成的队列为失败状态")

        # 初始检查现有队列
        queue_names = discover_image_generation_queues(REDIS_CONN)

        # 如果没有找到特定的队列，则添加固定的默认图像生成队列和default队列
        if not queue_names:
            logger.warning("未找到现有的图像生成队列，将监听默认队列")
            queue_names = {"default", "image_generation_default"}

            # 在Redis中创建image_generation_default队列键，确保它存在
            try:
                REDIS_CONN.sadd("rq:queues", "image_generation_default")
                logger.info("创建了默认图像生成队列: image_generation_default")
            except Exception as e:
                logger.error(f"创建默认队列失败: {e}")

        # 记录所有找到的队列名称
        logger.info(f"初始找到 {len(queue_names)} 个队列: {', '.join(queue_names)}")

        # 启动初始工作进程
        start_workers(queue_names, concurrency)

        # 启动进度更新线程
        MONITOR_THREAD = threading.Thread(
            target=update_progress_status, daemon=True)
        MONITOR_THREAD.start()
        logger.info("启动了任务进度更新线程")

        # 开始监控队列
        monitor_queues(concurrency)

    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在关闭工作进程...")
        signal_handler(signal.SIGINT, None)

    except Exception as e:
        logger.error(f"工作进程启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
