import os
import json
import uuid
import logging
import time
from typing import List, Dict, Any, Optional, Union
import redis
from rq import Queue, Worker
from rq.job import Job, JobStatus
from datetime import datetime, timedelta
from ...core.config import settings
from PIL import Image
import io
from redis.client import Pipeline

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 从环境变量获取Redis配置
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = int(os.getenv('REDIS_PORT', 6379))
redis_db = int(os.getenv('REDIS_DB', 0))

# 队列配置
QUEUE_PREFIX = "image_generation"
QUEUE_DATA_EXPIRY = 60 * 60 * 24  # 队列数据在Redis中的过期时间（秒），默认24小时
MAX_ACTIVE_QUEUES_PER_USER = 5    # 每个用户最大活跃队列数量
DEFAULT_CONCURRENCY = 5           # 默认并发数


class QueueService:
    """
    队列服务类，用于管理图像生成任务队列
    使用Redis作为后端存储，RQ作为任务队列
    """

    @staticmethod
    def get_redis_connection():
        """获取Redis连接"""
        try:
            return redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db
            )
        except Exception as e:
            logger.error(f"连接Redis失败: {e}")
            raise ConnectionError(f"无法连接到Redis服务: {e}")

    @staticmethod
    def create_generation_queue(
        user_id: str,
        tasks: List[Dict],
        model_id: int,
        project_id: int,
        concurrency: int = DEFAULT_CONCURRENCY
    ) -> Optional[str]:
        """
        创建图像生成队列

        Args:
            user_id: 用户ID
            tasks: 任务列表，每个任务包含image_id, image_url, prompt等字段
            model_id: 模型ID
            project_id: 项目ID
            concurrency: 并发数

        Returns:
            queue_id: 队列ID，如果创建失败则返回None
        """
        # 验证并限制并发数
        concurrency = max(1, min(10, concurrency))

        # 检查用户的活跃队列数量
        active_queues = QueueService.get_user_active_queues(user_id)
        if len(active_queues) >= MAX_ACTIVE_QUEUES_PER_USER:
            logger.warning(
                f"用户 {user_id} 活跃队列数量已达上限: {len(active_queues)}/{MAX_ACTIVE_QUEUES_PER_USER}")
            return None

        # 生成队列ID
        queue_id = f"{QUEUE_PREFIX}_{uuid.uuid4().hex}"

        # 创建队列元数据
        queue_data = {
            "queue_id": queue_id,
            "user_id": user_id,
            "project_id": project_id,
            "model_id": model_id,
            "created_at": datetime.now().isoformat(),
            "status": "waiting",  # waiting, processing, completed, failed
            "total_tasks": len(tasks),
            "total_completed": 0,
            "total_failed": 0,
            "completed_tasks": [],
            "failed_tasks": [],
            "concurrency": concurrency
        }

        # 连接Redis
        redis_conn = QueueService.get_redis_connection()

        try:
            # 保存队列元数据
            redis_conn.set(
                f"queue:{queue_id}:data",
                json.dumps(queue_data),
                ex=QUEUE_DATA_EXPIRY
            )

            # 保存队列任务
            redis_conn.set(
                f"queue:{queue_id}:tasks",
                json.dumps(tasks),
                ex=QUEUE_DATA_EXPIRY
            )

            # 保存用户队列映射
            user_queues_key = f"user:{user_id}:queues"
            user_queues = redis_conn.get(user_queues_key)

            if user_queues:
                user_queues = json.loads(user_queues)
                user_queues.append(queue_id)
            else:
                user_queues = [queue_id]

            redis_conn.set(
                user_queues_key,
                json.dumps(user_queues),
                ex=QUEUE_DATA_EXPIRY
            )

            # 启动队列处理（创建RQ队列并添加任务）
            QueueService._start_queue_processing(
                queue_id, tasks, model_id, project_id, concurrency)

            logger.info(f"创建队列成功: {queue_id}, 任务数: {len(tasks)}")
            return queue_id

        except Exception as e:
            logger.error(f"创建队列失败: {e}")
            # 清理可能已创建的数据
            redis_conn.delete(f"queue:{queue_id}:data")
            redis_conn.delete(f"queue:{queue_id}:tasks")
            return None

    @staticmethod
    def _start_queue_processing(
        queue_id: str,
        tasks: List[Dict],
        model_id: int,
        project_id: int,
        concurrency: int
    ):
        """
        启动队列处理

        Args:
            queue_id: 队列ID
            tasks: 任务列表
            model_id: 模型ID
            project_id: 项目ID
            concurrency: 并发数
        """
        try:
            # 导入处理函数，避免循环导入
            from .worker import process_image_task

            # 连接Redis
            redis_conn = QueueService.get_redis_connection()

            # 创建RQ队列
            rq_queue = Queue(
                name=queue_id,
                connection=redis_conn,
                default_timeout=600  # 10分钟超时
            )

            # 更新队列状态为处理中
            QueueService._update_queue_status(queue_id, "processing")

            # 将任务添加到队列
            for task in tasks:
                # 为每个任务添加队列ID和其他必要信息
                task_data = {
                    **task,
                    "queue_id": queue_id,
                    "model_id": model_id,
                    "project_id": project_id
                }

                # 添加任务到RQ队列
                rq_queue.enqueue(
                    process_image_task,
                    task_data,
                    job_id=f"{queue_id}_{task['image_id']}_{uuid.uuid4().hex}"
                )

            logger.info(
                f"队列 {queue_id} 已启动，任务数: {len(tasks)}, 并发数: {concurrency}")

        except Exception as e:
            logger.error(f"启动队列处理失败: {e}")
            # 将队列状态更新为失败
            QueueService._update_queue_status(
                queue_id,
                "failed",
                error=f"启动队列处理失败: {str(e)}"
            )

    @staticmethod
    def _update_queue_status(
        queue_id: str,
        status: str,
        error: str = None,
        completed_task: Dict = None,
        failed_task: Dict = None
    ):
        """
        更新队列状态

        Args:
            queue_id: 队列ID
            status: 状态 (waiting, processing, completed, failed)
            error: 错误信息
            completed_task: 完成的任务
            failed_task: 失败的任务
        """
        try:
            # 连接Redis
            redis_conn = QueueService.get_redis_connection()

            # 获取当前队列数据
            queue_data_key = f"queue:{queue_id}:data"
            queue_data_json = redis_conn.get(queue_data_key)

            if not queue_data_json:
                logger.warning(f"队列数据不存在: {queue_id}")
                return False

            queue_data = json.loads(queue_data_json)

            # 更新状态
            if status:
                queue_data["status"] = status

            # 更新错误信息
            if error:
                queue_data["error"] = error

            # 添加完成的任务
            if completed_task:
                queue_data["completed_tasks"].append(completed_task)
                queue_data["total_completed"] = len(
                    queue_data["completed_tasks"])

            # 添加失败的任务
            if failed_task:
                queue_data["failed_tasks"].append(failed_task)
                queue_data["total_failed"] = len(queue_data["failed_tasks"])

            # 检查是否所有任务都已完成或失败
            total_processed = queue_data["total_completed"] + \
                queue_data["total_failed"]

            if total_processed >= queue_data["total_tasks"]:
                # 所有任务都已处理完成
                if queue_data["total_failed"] == queue_data["total_tasks"]:
                    # 所有任务都失败
                    queue_data["status"] = "failed"
                else:
                    # 至少有一个任务成功完成
                    queue_data["status"] = "completed"

                # 更新完成时间
                queue_data["completed_at"] = datetime.now().isoformat()

            # 保存更新后的队列数据
            redis_conn.set(
                queue_data_key,
                json.dumps(queue_data),
                ex=QUEUE_DATA_EXPIRY
            )

            return True

        except Exception as e:
            logger.error(f"更新队列状态失败: {e}")
            return False

    @staticmethod
    def get_queue_status(queue_id: str) -> Optional[Dict]:
        """
        获取队列状态

        Args:
            queue_id: 队列ID

        Returns:
            queue_data: 队列状态数据，如果队列不存在则返回None
        """
        try:
            # 连接Redis
            redis_conn = QueueService.get_redis_connection()

            # 获取队列数据
            queue_data_key = f"queue:{queue_id}:data"
            queue_data_json = redis_conn.get(queue_data_key)

            if not queue_data_json:
                logger.warning(f"队列数据不存在: {queue_id}")
                return None

            return json.loads(queue_data_json)

        except Exception as e:
            logger.error(f"获取队列状态失败: {e}")
            return None

    @staticmethod
    def cancel_queue(queue_id: str, user_id: str) -> bool:
        """
        取消队列

        Args:
            queue_id: 队列ID
            user_id: 用户ID（用于验证权限）

        Returns:
            success: 是否成功取消队列
        """
        try:
            # 连接Redis
            redis_conn = QueueService.get_redis_connection()

            # 获取队列数据
            queue_data_key = f"queue:{queue_id}:data"
            queue_data_json = redis_conn.get(queue_data_key)

            if not queue_data_json:
                logger.warning(f"队列数据不存在: {queue_id}")
                return False

            queue_data = json.loads(queue_data_json)

            # 验证用户权限
            if str(queue_data.get("user_id")) != str(user_id):
                logger.warning(f"用户 {user_id} 无权取消队列 {queue_id}")
                return False

            # 获取队列中所有任务的Job ID
            try:
                # 创建RQ队列对象
                rq_queue = Queue(name=queue_id, connection=redis_conn)

                # 取消所有未完成的作业
                for job in rq_queue.get_jobs():
                    job.cancel()
                    logger.info(f"已取消作业: {job.id}")

                # 清空队列
                rq_queue.empty()
                logger.info(f"已清空队列: {queue_id}")

            except Exception as e:
                logger.error(f"取消队列作业失败: {e}")

            # 更新队列状态为失败
            queue_data["status"] = "failed"
            queue_data["error"] = "队列已被用户取消"
            queue_data["cancelled_at"] = datetime.now().isoformat()

            # 保存更新后的队列数据
            redis_conn.set(
                queue_data_key,
                json.dumps(queue_data),
                ex=QUEUE_DATA_EXPIRY
            )

            logger.info(f"队列 {queue_id} 已被用户 {user_id} 取消")
            return True

        except Exception as e:
            logger.error(f"取消队列失败: {e}")
            return False

    @staticmethod
    def get_user_active_queues(user_id: str) -> List[Dict]:
        """
        获取用户的活跃队列

        Args:
            user_id: 用户ID

        Returns:
            active_queues: 活跃队列列表
        """
        try:
            # 连接Redis
            redis_conn = QueueService.get_redis_connection()

            # 获取用户队列映射
            user_queues_key = f"user:{user_id}:queues"
            user_queues_json = redis_conn.get(user_queues_key)

            if not user_queues_json:
                return []

            user_queues = json.loads(user_queues_json)
            active_queues = []

            # 获取每个队列的状态
            for queue_id in user_queues:
                queue_data = QueueService.get_queue_status(queue_id)

                if queue_data and queue_data["status"] in ["waiting", "processing"]:
                    # 只返回活跃的队列（状态为等待中或处理中）
                    active_queues.append(queue_data)

            # 按创建时间排序，最新的在前面
            active_queues.sort(key=lambda q: q.get(
                "created_at", ""), reverse=True)

            return active_queues

        except Exception as e:
            logger.error(f"获取用户活跃队列失败: {e}")
            return []

    @staticmethod
    def mark_unfinished_queues_as_failed() -> int:
        """
        将所有未完成的队列标记为失败
        通常在服务启动时调用，处理之前未正常完成的队列

        Returns:
            updated_count: 更新的队列数量
        """
        try:
            # 连接Redis
            redis_conn = QueueService.get_redis_connection()

            # 获取所有队列数据键
            queue_data_keys = redis_conn.keys("queue:*:data")
            updated_count = 0

            for key in queue_data_keys:
                try:
                    key_str = key.decode('utf-8')
                    queue_id = key_str.split(':')[1]

                    # 获取队列数据
                    queue_data_json = redis_conn.get(key_str)

                    if not queue_data_json:
                        continue

                    queue_data = json.loads(queue_data_json)

                    # 检查队列状态
                    if queue_data["status"] in ["waiting", "processing"]:
                        # 更新为失败状态
                        queue_data["status"] = "failed"
                        queue_data["error"] = "服务重启，队列未能完成"

                        # 保存更新后的队列数据
                        redis_conn.set(
                            key_str,
                            json.dumps(queue_data),
                            ex=QUEUE_DATA_EXPIRY
                        )

                        updated_count += 1
                        logger.info(f"队列 {queue_id} 已标记为失败")

                except Exception as e:
                    logger.error(f"处理队列数据键 {key} 时出错: {e}")

            return updated_count

        except Exception as e:
            logger.error(f"标记未完成队列失败: {e}")
            return 0

    @staticmethod
    def report_task_success(queue_id: str, task_data: Dict, results: List[Dict]) -> bool:
        """
        报告任务成功

        Args:
            queue_id: 队列ID
            task_data: 任务数据
            results: 任务结果列表

        Returns:
            success: 是否成功报告
        """
        try:
            # 连接Redis
            redis_conn = QueueService.get_redis_connection()

            # 获取任务ID
            image_id = task_data.get("image_id")
            job_id = task_data.get("job_id")

            if not image_id:
                logger.warning(f"任务数据缺少image_id: {task_data}")
                return False

            # 构建完成的任务数据
            completed_task = {
                "image_id": image_id,
                "completed_at": datetime.now().isoformat(),
                "results": results
            }

            # 将任务ID添加到已完成任务集合
            completed_tasks_key = f"queue:{queue_id}:completed_tasks"
            redis_conn.sadd(completed_tasks_key, image_id)
            redis_conn.expire(completed_tasks_key, QUEUE_DATA_EXPIRY)

            # 更新任务进度状态为已完成
            if job_id:
                progress_key = f"task_progress:{job_id}"
                redis_conn.hset(progress_key, "progress", 100)
                redis_conn.hset(progress_key, "status", "completed")
                redis_conn.expire(progress_key, 3600)  # 1小时过期

            # 更新队列状态
            return QueueService._update_queue_status(
                queue_id,
                status=None,  # 不更改状态，由_update_queue_status根据完成情况决定
                completed_task=completed_task
            )

        except Exception as e:
            logger.error(f"报告任务成功失败: {e}")
            return False

    @staticmethod
    def report_task_failure(queue_id: str, task_data: Dict, error: str) -> bool:
        """
        报告任务失败

        Args:
            queue_id: 队列ID
            task_data: 任务数据
            error: 错误信息

        Returns:
            success: 是否成功报告
        """
        try:
            # 连接Redis
            redis_conn = QueueService.get_redis_connection()

            # 获取任务ID
            image_id = task_data.get("image_id")
            job_id = task_data.get("job_id")

            if not image_id:
                logger.warning(f"任务数据缺少image_id: {task_data}")
                return False

            # 构建失败的任务数据
            failed_task = {
                "image_id": image_id,
                "failed_at": datetime.now().isoformat(),
                "error": error
            }

            # 将任务ID添加到失败任务集合
            failed_tasks_key = f"queue:{queue_id}:failed_tasks"
            redis_conn.sadd(failed_tasks_key, image_id)
            redis_conn.expire(failed_tasks_key, QUEUE_DATA_EXPIRY)

            # 更新任务进度状态为失败
            if job_id:
                progress_key = f"task_progress:{job_id}"
                redis_conn.hset(progress_key, "progress", 100)
                redis_conn.hset(progress_key, "status", "failed")
                redis_conn.expire(progress_key, 3600)  # 1小时过期

            # 更新队列状态
            return QueueService._update_queue_status(
                queue_id,
                status=None,  # 不更改状态，由_update_queue_status根据完成情况决定
                failed_task=failed_task
            )

        except Exception as e:
            logger.error(f"报告任务失败失败: {e}")
            return False

    def create_queue(self, tasks, model_id, project_id, concurrency=3, username="admin") -> str:
        """创建图像生成队列

        Args:
            tasks: 要处理的任务列表，每个任务应包含 image_id 和 image_url
            model_id: 使用的模型ID
            project_id: 项目ID
            concurrency: 并发处理的任务数，默认为3
            username: 用户名，默认为admin

        Returns:
            queue_id: 队列ID
        """
        # 连接到Redis
        if not hasattr(self, 'redis_conn') or self.redis_conn is None:
            self.redis_conn = QueueService.get_redis_connection()

        # 创建唯一的队列ID
        queue_id = f"image_generation_{uuid.uuid4().hex}"

        # 创建Redis队列
        img_queue = Queue(
            queue_id,
            connection=self.redis_conn,
            default_timeout=1800  # 30分钟超时
        )

        # 记录队列创建
        logger.info(f"创建队列: {queue_id}, Redis键: rq:queue:{queue_id}")

        # 预处理任务，确保图片大小合适
        processed_tasks = []
        for task in tasks:
            processed_task = self._preprocess_task(task, project_id)
            processed_tasks.append(processed_task)

        # 将队列信息存储在Redis中
        queue_info = {
            "id": queue_id,
            "status": "created",
            "model_id": model_id,
            "project_id": project_id,
            "username": username,
            "concurrency": concurrency,
            "created_at": datetime.now().isoformat(),
            "total_tasks": len(processed_tasks),
            "completed_tasks": 0,
            "failed_tasks": 0,
            "last_updated": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=1)).isoformat()
        }

        # 确保队列可以被worker发现的关键步骤
        pipe = self.redis_conn.pipeline()

        # 1. 直接使用队列ID作为键（用于直接模式查找）
        pipe.setex(
            queue_id,  # 直接设置键名为queue_id
            86400,  # 1天过期
            "queue_exists"  # 只需要键存在，值不重要
        )

        # 2. 添加到rq:queues集合中（RQ的标准做法）
        pipe.sadd("rq:queues", queue_id)

        # 3. 保存详细队列信息
        pipe.setex(
            f"queue:{queue_id}:info",
            86400,  # 1天过期
            json.dumps(queue_info)
        )

        # 4. 设置worker监听触发器
        pipe.setex(
            f"worker:listen:{queue_id}",
            86400,  # 1天过期
            "1"
        )

        # 执行所有Redis操作
        pipe.execute()

        logger.info(f"在Redis中创建了队列相关键: {queue_id}")

        # 保存任务到Redis列表，用于UI状态跟踪
        if processed_tasks:
            pipe = self.redis_conn.pipeline()
            key = f"queue:{queue_id}:tasks"
            for task in processed_tasks:
                pipe.rpush(key, json.dumps(task))
            pipe.expire(key, 86400)  # 1天过期
            pipe.execute()

        # 将任务添加到处理队列中
        for task in processed_tasks:
            job = img_queue.enqueue(
                "app.services.queue.worker.process_image_task",
                {
                    "image_id": task["image_id"],
                    "image_url": task["image_url"],
                    "prompt": task.get("prompt"),
                    "model_id": model_id,
                    "project_id": project_id,
                    "queue_id": queue_id,
                    "seed": task.get("seed"),
                    "width": task.get("width"),
                    "height": task.get("height"),
                    "enhance": task.get("enhance", False)
                },
                job_id=f"{queue_id}_{task['image_id']}_{uuid.uuid4().hex[:24]}"
            )
            logger.info(f"添加任务到队列: {queue_id}, 任务ID: {job.id}")

        # 添加队列ID到活跃队列集合
        self.redis_conn.sadd(f"user:{username}:active_queues", queue_id)
        self.redis_conn.expire(f"user:{username}:active_queues", 86400)  # 1天过期

        logger.info(f"成功创建队列 {queue_id} 并添加了 {len(processed_tasks)} 个任务")

        return queue_id

    def _preprocess_task(self, task: Dict[str, Any], project_id: int) -> Dict[str, Any]:
        """预处理任务，确保图片大小合适

        Args:
            task: 任务信息，包含 image_id 和 image_url
            project_id: 项目ID

        Returns:
            处理后的任务信息
        """
        processed_task = task.copy()

        # 图片URL处理
        if "image_url" in task and task["image_url"]:
            image_url = task["image_url"]

            # 如果是本地URL，获取文件路径
            if image_url.startswith(('http://localhost', 'https://localhost')):
                # 提取文件路径
                file_path = image_url.split('/uploads/', 1)[-1]
                absolute_path = os.path.join(
                    '/Users/wangjunyan/image_project/backend/uploads', file_path)

                try:
                    # 确保文件存在
                    if os.path.exists(absolute_path):
                        # 读取图片并检查大小
                        with Image.open(absolute_path) as img:
                            width, height = img.size

                            # 如果图片尺寸超过限制，调整大小
                            if width > 2048 or height > 2048:
                                logging.info(
                                    f"图片尺寸超过限制: {width}x{height}, 调整大小")

                                # 计算新尺寸，保持宽高比
                                ratio = min(2048 / width, 2048 / height)
                                new_width = int(width * ratio)
                                new_height = int(height * ratio)

                                # 调整图片大小
                                img = img.resize(
                                    (new_width, new_height), Image.LANCZOS)

                                # 创建新的文件名和路径
                                filename_parts = os.path.basename(
                                    absolute_path).split('.')
                                base_name = '.'.join(
                                    filename_parts[:-1]) if len(filename_parts) > 1 else filename_parts[0]
                                extension = filename_parts[-1] if len(
                                    filename_parts) > 1 else 'jpg'
                                new_filename = f"{base_name}_resized.{extension}"

                                upload_dir = os.path.dirname(absolute_path)
                                new_path = os.path.join(
                                    upload_dir, new_filename)

                                # 保存调整大小后的图片
                                img.save(new_path)

                                # 更新任务URL为新图片
                                base_url = task["image_url"].rsplit('/', 1)[0]
                                processed_task["image_url"] = f"{base_url}/{new_filename}"
                                processed_task["width"] = new_width
                                processed_task["height"] = new_height

                                logging.info(
                                    f"图片已调整大小: {new_width}x{new_height}, 新路径: {new_path}")
                except Exception as e:
                    logging.error(f"处理图片出错: {str(e)}")

        return processed_task
