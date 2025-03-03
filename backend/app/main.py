from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import subprocess
import os
import sys
import time
import logging
import multiprocessing
import signal
import psutil
import asyncio

from .core.config import settings
from .database.database import init_db
from .api.endpoints import auth, generation
from .api.endpoints.generation import router as generation_router
from .api.endpoints.generation import image_router
from .api.endpoints.projects import router as projects_router
from .routers.generation import router as queue_router
from .services.queue_worker import QueueWorker

logging.basicConfig(level=logging.DEBUG)

# 初始化数据库
init_db()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# worker 进程引用
worker_process = None

# 全局队列工作器实例
queue_worker = None

# 注册路由
app.include_router(
    auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(
    generation_router,
    prefix=f"{settings.API_V1_STR}/generation",
    tags=["generation"]
)
app.include_router(
    image_router,
    tags=["images"]
)
app.include_router(
    projects_router,
    prefix=f"{settings.API_V1_STR}/projects",
    tags=["projects"]
)
# 注册队列路由
app.include_router(
    queue_router,
    prefix=f"{settings.API_V1_STR}/generation",
    tags=["queue"]
)


def cleanup_worker():
    """清理 worker 进程"""
    global worker_process

    if worker_process and worker_process.is_alive():
        try:
            logging.info(f"终止 Worker 进程 (PID: {worker_process.pid})...")

            # 发送 SIGTERM 信号，让 worker 优雅关闭
            os.kill(worker_process.pid, signal.SIGTERM)

            # 等待进程终止，最多等待 5 秒
            for _ in range(50):  # 50 * 0.1 = 5 seconds
                if not worker_process.is_alive():
                    break
                time.sleep(0.1)

            # 如果进程仍然存活，强制终止
            if worker_process.is_alive():
                logging.warning("Worker 进程未响应 SIGTERM，发送 SIGKILL...")
                os.kill(worker_process.pid, signal.SIGKILL)
                worker_process.join(1)  # 再等待 1 秒

            logging.info("Worker 进程已终止")
        except Exception as e:
            logging.error(f"清理 worker 进程时出错: {str(e)}")

    # 尝试查找并终止可能的僵尸 worker 进程
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # 检查是否是 Python 进程
                if proc.info['name'] and 'python' in proc.info['name'].lower():
                    cmdline = " ".join(proc.info['cmdline'] or [])
                    # 检查命令行是否包含 worker.py
                    if 'worker.py' in cmdline:
                        logging.warning(
                            f"发现残留的 worker 进程: PID={proc.pid}, 命令行={cmdline}")
                        # 尝试终止
                        try:
                            proc.send_signal(signal.SIGTERM)
                            logging.info(f"已发送 SIGTERM 到 worker 进程 {proc.pid}")

                            # 等待 2 秒看是否终止
                            try:
                                proc.wait(timeout=2)
                                logging.info(f"Worker 进程 {proc.pid} 已终止")
                            except psutil.TimeoutExpired:
                                # 如果超时，发送 SIGKILL
                                logging.warning(
                                    f"Worker 进程 {proc.pid} 未响应 SIGTERM，发送 SIGKILL")
                                proc.send_signal(signal.SIGKILL)
                        except psutil.NoSuchProcess:
                            logging.info(f"Worker 进程 {proc.pid} 已不存在")
                        except Exception as e:
                            logging.error(f"终止 worker 进程 {proc.pid} 时出错: {e}")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                logging.debug(f"检查进程时出错: {e}")
    except ImportError:
        logging.warning("无法导入 psutil，跳过额外的进程清理")
    except Exception as e:
        logging.error(f"查找僵尸 worker 进程时出错: {e}")

    # 重置全局 worker_process 变量
    worker_process = None


def run_worker():
    """运行 worker 进程"""
    worker_script = os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))), "worker.py")

    try:
        # 使用 Python 解释器运行 worker.py 脚本
        logging.info(f"正在启动 worker 进程: {worker_script}")

        # 使用环境变量标记这是从主应用启动的
        env = os.environ.copy()
        env['LAUNCHED_FROM_MAIN'] = '1'

        # 使用 subprocess 运行 worker 脚本
        process = subprocess.Popen(
            [sys.executable, worker_script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # 读取并记录 worker 的输出
        stdout, stderr = process.communicate()

        # 检查进程的退出状态
        if process.returncode != 0:
            logging.error(f"Worker 进程异常退出 (退出码: {process.returncode})")
            if stdout:
                logging.debug(f"Worker 输出:\n{stdout}")
            if stderr:
                logging.error(f"Worker 错误:\n{stderr}")
            return False

        logging.info("Worker 进程正常结束")
        return True

    except subprocess.CalledProcessError as e:
        logging.error(f"Worker 进程启动失败 (退出码: {e.returncode}): {e}")
        if hasattr(e, 'output') and e.output:
            logging.error(f"错误输出: {e.output}")
        if hasattr(e, 'stderr') and e.stderr:
            logging.error(f"标准错误: {e.stderr}")
    except Exception as e:
        logging.error(f"Worker 启动异常: {str(e)}")

    return False


def monitor_worker():
    """监控 worker 进程并在必要时重启"""
    retry_count = 0
    max_retries = 10  # 增加最大尝试次数
    backoff_time = 1  # 初始退避时间（秒）
    consecutive_rapid_failures = 0  # 连续快速失败的次数
    last_start_time = 0

    while True:
        current_time = time.time()
        time_since_last_start = current_time - last_start_time

        # 如果上次启动是最近30秒内，这被视为快速失败
        if time_since_last_start < 30:
            consecutive_rapid_failures += 1
            logging.warning(f"Worker 快速失败 {consecutive_rapid_failures} 次")

            # 如果连续快速失败次数过多，增加等待时间
            if consecutive_rapid_failures > 3:
                extra_wait = consecutive_rapid_failures * 10  # 每次快速失败多等10秒
                logging.warning(f"检测到频繁失败，额外等待 {extra_wait} 秒...")
                time.sleep(extra_wait)
        else:
            # 如果 worker 运行较长时间后才失败，重置计数
            consecutive_rapid_failures = 0

        last_start_time = time.time()

        # 运行 worker
        success = run_worker()

        # 如果成功运行，重置尝试计数
        if success:
            retry_count = 0
            backoff_time = 1
            continue

        # 如果 worker 退出，尝试重启
        retry_count += 1
        if retry_count > max_retries:
            logging.error(f"Worker 进程已连续失败 {retry_count} 次，停止尝试")
            # 等待较长时间后再次尝试
            time.sleep(300)  # 5分钟后重试
            retry_count = 0
            continue

        # 计算退避时间（指数增长）
        sleep_time = backoff_time * (2 ** (retry_count - 1))
        sleep_time = min(sleep_time, 120)  # 最长不超过2分钟

        logging.info(
            f"将在 {sleep_time} 秒后尝试重启 Worker (尝试 {retry_count}/{max_retries})...")
        time.sleep(sleep_time)


@app.on_event("startup")
async def startup_event():
    """应用启动时执行的操作"""
    global queue_worker
    
    logging.info("应用启动，准备启动队列工作器...")
    
    # 初始化队列工作器
    queue_worker = QueueWorker()
    
    # 启动后台任务来处理队列
    asyncio.create_task(process_queues())
    
    logging.info("队列工作器已启动")

async def process_queues():
    """处理队列的后台任务"""
    # 记录正在处理的队列
    processing_queues = set()
    
    while True:
        try:
            # 获取所有活跃的队列
            active_queues = queue_worker.redis_service.get_all_active_queues()
            
            # 为每个等待中的队列启动处理任务
            for queue_info in active_queues:
                queue_id = queue_info["queue_id"]
                status = queue_info.get("status")
                
                # 检查队列是否仍然存在且状态正确
                current_info = queue_worker.redis_service.get_queue_status(queue_id)
                if not current_info:
                    logging.warning(f"队列 {queue_id} 已不存在，跳过处理")
                    continue
                    
                current_status = current_info.get("status")
                
                # 检查是否有未完成的任务
                total_tasks = int(current_info.get("total_tasks", 0))
                completed_tasks = int(current_info.get("completed_tasks", 0))
                failed_tasks = int(current_info.get("failed_tasks", 0))
                
                # 如果所有任务都已完成,更新状态并跳过
                if completed_tasks + failed_tasks >= total_tasks:
                    if current_status != "completed":
                        logging.info(f"队列 {queue_id} 所有任务已完成,更新状态为completed")
                        queue_worker.redis_service.update_queue_status(queue_id, "completed")
                    continue
                
                # 只处理等待中、处理中或pending的队列
                if current_status not in ["waiting", "pending", "processing"]:
                    logging.debug(f"队列 {queue_id} 当前状态为 {current_status}，跳过处理")
                    continue
                
                # 只处理未在处理中的队列
                if queue_id not in processing_queues:
                    logging.info(f"开始处理新队列: {queue_id}, 状态: {current_status}, 已完成: {completed_tasks}/{total_tasks}")
                    processing_queues.add(queue_id)
                    
                    # 创建任务并设置回调来移除已完成的队列
                    task = asyncio.create_task(queue_worker.start_queue(queue_id))
                    
                    def cleanup_queue(future):
                        try:
                            # 检查任务是否有异常
                            if future.exception():
                                logging.error(f"处理队列 {queue_id} 时发生错误: {future.exception()}")
                            processing_queues.discard(queue_id)
                            logging.info(f"队列 {queue_id} 处理完成，从处理集合中移除")
                        except Exception as e:
                            logging.error(f"清理队列 {queue_id} 时发生错误: {str(e)}")
                    
                    task.add_done_callback(cleanup_queue)
            
            # 每5秒检查一次新的队列
            await asyncio.sleep(5)
            
        except Exception as e:
            logging.error(f"处理队列时出错: {str(e)}")
            await asyncio.sleep(5)  # 出错时也等待5秒

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行的操作"""
    global queue_worker
    
    if queue_worker:
        queue_worker.stop()
        logging.info("队列工作器已停止")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
