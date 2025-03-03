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

from .core.config import settings
from .database.database import init_db
from .api.endpoints import auth, generation
from .api.endpoints.generation import router as generation_router
from .api.endpoints.generation import image_router
from .api.endpoints.projects import router as projects_router
from .api.endpoints.i2v_api import router as i2v_router
from .routers.generation import router as queue_router

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
    prefix=f"{settings.API_V1_STR}/images",
    tags=["images"]
)
app.include_router(
    projects_router,
    prefix=f"{settings.API_V1_STR}/projects",
    tags=["projects"]
)
app.include_router(
    i2v_router,
    prefix=f"{settings.API_V1_STR}/i2v",
    tags=["image-to-video"],
)
# 注册队列路由
app.include_router(
    queue_router,
    prefix=f"{settings.API_V1_STR}/queue",
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
    global worker_process

    logging.info("应用启动，准备管理 worker 进程...")

    # 先清理可能存在的旧进程
    cleanup_worker()

    # 额外清理：尝试删除 Redis 中的 worker 数据
    try:
        import redis
        from dotenv import load_dotenv
        from .services.queue.queue_service import QueueService

        # 加载环境变量
        load_dotenv()

        # 获取 Redis 连接
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_db = int(os.getenv('REDIS_DB', 0))

        logging.info(
            f"连接到 Redis 进行 worker 数据清理: {redis_host}:{redis_port}/{redis_db}")
        redis_conn = redis.Redis(host=redis_host, port=redis_port, db=redis_db)

        # 清理 worker 相关的 Redis 键
        patterns_to_clean = [
            "rq:worker:*",
            "rq:workers",
            "rq:workers:*",
            "rq:wqueue:*"
        ]

        for pattern in patterns_to_clean:
            try:
                keys = redis_conn.keys(pattern)
                if keys:
                    logging.info(f"发现 {len(keys)} 个 '{pattern}' 键，将全部删除")
                    for key in keys:
                        redis_conn.delete(key)
                        logging.debug(f"已删除键: {key.decode('utf-8')}")
            except Exception as e:
                logging.warning(f"清理 Redis 键模式 '{pattern}' 时出错: {e}")

        # 检查所有未完成的队列任务，将其状态修改为失败
        try:
            logging.info("检查未完成的队列任务...")
            # 使用QueueService类的方法处理未完成的队列任务
            updated_count = QueueService.mark_unfinished_queues_as_failed()

            if updated_count > 0:
                logging.info(f"已将 {updated_count} 个未完成的队列任务状态修改为失败")
            else:
                logging.info("未发现未完成的队列任务")

        except Exception as e:
            logging.error(f"检查未完成队列任务时出错: {e}")

        # 等待清理完成
        logging.info("Redis 清理完成，等待 2 秒确保操作生效...")
        time.sleep(2)

    except ImportError:
        logging.warning("无法导入 redis，跳过 Redis 数据清理")
    except Exception as e:
        logging.error(f"清理 Redis 数据时出错: {e}")

    logging.info("启动 Redis 队列工作进程...")

    # 创建并启动 worker 子进程（使用监控函数）
    worker_process = multiprocessing.Process(target=monitor_worker)
    worker_process.daemon = True  # 设置为守护进程，主进程退出时自动退出
    worker_process.start()

    logging.info(f"Redis 队列工作进程监控器已在后台启动 (PID: {worker_process.pid})")

    # 记录一些系统信息
    try:
        import platform
        logging.info(
            f"系统信息: {platform.system()} {platform.release()}, Python {platform.python_version()}")
        logging.info(
            f"进程信息: 主进程 PID={os.getpid()}, Worker 监控进程 PID={worker_process.pid}")
    except Exception as e:
        logging.error(f"获取系统信息时出错: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行的操作"""
    logging.info("应用关闭，清理资源...")
    cleanup_worker()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
