import json
from typing import List, Dict, Any, Optional
from redis import Redis
from datetime import datetime
import uuid
from ..core.config import settings
import logging

class RedisQueueService:
    def __init__(self):
        self.redis = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
            encoding='utf-8'
        )
        self.queue_key = "image_tasks"  # 存储所有待处理任务
        self.task_key = "task_info:"    # 存储任务详情
        self.queue_prefix = "queue:"      # 队列前缀
        self.queue_info_prefix = "queue_info:" # 队列信息前缀
        self.task_prefix = "task:"       # 任务前缀
        self.queue_expiry = 86400         # 队列过期时间（24小时）

    def create_task(self, task_data: Dict[str, Any]) -> str:
        """创建新任务"""
        try:
            # 生成任务ID
            task_id = str(uuid.uuid4())
            
            # 构建任务信息
            task_info = {
                "task_id": task_id,
                "status": "pending",     # 任务状态：pending/processing/completed/failed
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            
            # 将字典数据序列化
            for key, value in task_data.items():
                if isinstance(value, (dict, list)):
                    task_info[key] = json.dumps(value)
                else:
                    task_info[key] = str(value)
            
            # 使用 HSET 存储任务信息
            self.redis.hset(f"{self.task_key}{task_id}", mapping=task_info)
            
            # 将任务添加到队列
            self.redis.rpush(self.queue_key, task_id)
            
            return task_id
        except Exception as e:
            logging.error(f"创建任务失败: {e}")
            raise

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        try:
            # 获取任务信息
            task_info = self.redis.hgetall(f"{self.task_key}{task_id}")
            if not task_info:
                return None
                
            # 反序列化数据
            result = {}
            for key, value in task_info.items():
                try:
                    # 尝试解析 JSON 数据
                    result[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # 如果不是 JSON 格式，直接使用原始值
                    result[key] = value
                    
            # 转换数值类型
            if "progress" in result:
                try:
                    result["progress"] = float(result["progress"])
                except (ValueError, TypeError):
                    result["progress"] = 0.0
                
            return result
        except Exception as e:
            logging.error(f"获取任务状态失败: {e}")
            return None

    def update_task_status(self, task_id: str, status: str, additional_data: Dict[str, Any] = None):
        """更新任务状态"""
        try:
            updates = {
                "status": status,
                "updated_at": datetime.now().isoformat()
            }
            
            if additional_data:
                # 序列化复杂数据类型
                for key, value in additional_data.items():
                    if isinstance(value, (dict, list)):
                        updates[key] = json.dumps(value)
                    else:
                        updates[key] = str(value)
                    
            self.redis.hset(f"{self.task_key}{task_id}", mapping=updates)
            return True
        except Exception as e:
            logging.error(f"更新任务状态失败: {e}")
            return False

    def get_next_task(self) -> Optional[str]:
        """获取下一个待处理的任务ID"""
        try:
            return self.redis.lpop(self.queue_key)
        except Exception as e:
            logging.error(f"获取下一个任务失败: {e}")
            return None

    def get_user_tasks(self, user_id: str) -> List[Dict]:
        """获取用户的所有任务"""
        tasks = []
        try:
            # 获取所有任务键
            for key in self.redis.scan_iter(f"{self.task_key}*"):
                task_info = self.redis.hgetall(key)
                if task_info.get("user_id") == user_id:
                    tasks.append(task_info)
            return tasks
        except Exception as e:
            logging.error(f"获取用户任务失败: {e}")
            return []

    def create_queue(self, tasks: List[Dict], model_id: int, project_id: int, user_id: str, concurrency: int = 5) -> str:
        queue_id = str(uuid.uuid4())
        queue_key = f"{self.queue_prefix}{queue_id}"
        queue_info_key = f"{self.queue_info_prefix}{queue_id}"
        
        # 存储队列基本信息
        queue_info = {
            "user_id": user_id,
            "model_id": str(model_id),
            "project_id": str(project_id),
            "concurrency": str(concurrency),
            "total_tasks": str(len(tasks)),
            "completed_tasks": "0",
            "failed_tasks": "0",
            "status": "waiting",  # 初始状态为 waiting
            "created_at": datetime.now().isoformat(),
        }
        
        # 将任务添加到队列
        pipeline = self.redis.pipeline()
        for task in tasks:
            task_id = str(uuid.uuid4())
            task_key = f"{self.task_prefix}{task_id}"
            task_data = {
                "task_id": task_id,
                "queue_id": queue_id,
                "status": "waiting",  # 任务状态为 waiting
                "model_id": str(model_id),
                "project_id": str(project_id),
                "image_id": str(task["image_id"]),
                "image_url": task["image_url"],
                "prompt": task["prompt"],
                "width": str(task.get("width", 1024)),
                "height": str(task.get("height", 1024)),
                "seeds": json.dumps(task.get("seeds", [])),
                "source_image_path": task["source_image_path"]
            }
            # 存储任务详情
            pipeline.hset(task_key, mapping=task_data)
            pipeline.expire(task_key, self.queue_expiry)
            # 将任务ID添加到队列
            pipeline.rpush(queue_key, task_id)
            
        # 创建任务状态列表
        completed_tasks_key = f"{self.queue_prefix}{queue_id}:completed_tasks"
        failed_tasks_key = f"{self.queue_prefix}{queue_id}:failed_tasks"
        processing_tasks_key = f"{self.queue_prefix}{queue_id}:processing_tasks"
        pipeline.expire(completed_tasks_key, self.queue_expiry)
        pipeline.expire(failed_tasks_key, self.queue_expiry)
        pipeline.expire(processing_tasks_key, self.queue_expiry)
        
        # 存储队列信息
        pipeline.hset(queue_info_key, mapping=queue_info)
        pipeline.expire(queue_info_key, self.queue_expiry)
        pipeline.expire(queue_key, self.queue_expiry)
        pipeline.execute()
        
        return queue_id

    def get_queue_status(self, queue_id: str) -> Optional[Dict[str, Any]]:
        """获取队列状态（非阻塞）"""
        try:
            # 获取队列基本信息
            queue_info_key = f"{self.queue_info_prefix}{queue_id}"
            queue_info = self.redis.hgetall(queue_info_key)
            
            if not queue_info:
                return None
                
            # 获取任务状态列表
            completed_tasks_key = f"{self.queue_prefix}{queue_id}:completed_tasks"
            failed_tasks_key = f"{self.queue_prefix}{queue_id}:failed_tasks"
            processing_tasks_key = f"{self.queue_prefix}{queue_id}:processing_tasks"
            
            # 获取各类任务
            completed_tasks = []
            failed_tasks = []
            current_tasks = []
            
            try:
                completed_tasks = [json.loads(task) for task in self.redis.lrange(completed_tasks_key, 0, -1)]
            except Exception as e:
                logging.error(f"获取已完成任务失败: {e}")
                
            try:
                failed_tasks = [json.loads(task) for task in self.redis.lrange(failed_tasks_key, 0, -1)]
            except Exception as e:
                logging.error(f"获取失败任务失败: {e}")
                
            try:
                current_tasks = [json.loads(task) for task in self.redis.lrange(processing_tasks_key, 0, -1)]
            except Exception as e:
                logging.error(f"获取处理中任务失败: {e}")
            
            # 计算任务数量
            total_tasks = int(queue_info.get("total_tasks", 0))
            completed_count = len(completed_tasks)
            failed_count = len(failed_tasks)
            current_count = len(current_tasks)
            
            # 计算待处理任务数
            pending_count = total_tasks - completed_count - failed_count - current_count
            
            # 更新队列状态
            current_status = self._calculate_queue_status(queue_id, total_tasks, completed_count, failed_count)
            
            # 构建返回数据
            queue_info.update({
                "completed_tasks": completed_count,
                "total_completed": completed_count,
                "failed_tasks": failed_count,
                "pending_tasks": pending_count,
                "current_tasks": current_tasks,
                "completed_task_details": completed_tasks,
                "failed_task_details": failed_tasks,
                "status": current_status
            })
            
            return queue_info
                
        except Exception as e:
            logging.error(f"获取队列状态失败: {str(e)}")
            return None

    def get_queue_tasks(self, queue_id: str) -> List[Dict[str, Any]]:
        """获取当前正在处理的任务"""
        processing_tasks_key = f"{self.queue_prefix}{queue_id}:processing_tasks"
        try:
            # 使用 pipeline 进行原子操作
            with self.redis.pipeline() as pipe:
                pipe.lrange(processing_tasks_key, 0, -1)
                processing_tasks = pipe.execute()[0]
                return [json.loads(task) for task in processing_tasks]
        except Exception as e:
            logging.error(f"获取处理中的任务失败: {str(e)}")
            return []

    def get_completed_tasks(self, queue_id: str) -> List[Dict[str, Any]]:
        """获取已完成的任务详情"""
        completed_tasks_key = f"{self.queue_prefix}{queue_id}:completed_tasks"
        try:
            with self.redis.pipeline() as pipe:
                pipe.lrange(completed_tasks_key, 0, -1)
                completed_tasks = pipe.execute()[0]
                return [json.loads(task) for task in completed_tasks]
        except Exception as e:
            logging.error(f"获取已完成的任务失败: {str(e)}")
            return []
        
    def get_failed_tasks(self, queue_id: str) -> List[Dict[str, Any]]:
        """获取失败的任务详情"""
        failed_tasks_key = f"{self.queue_prefix}{queue_id}:failed_tasks"
        try:
            with self.redis.pipeline() as pipe:
                pipe.lrange(failed_tasks_key, 0, -1)
                failed_tasks = pipe.execute()[0]
                return [json.loads(task) for task in failed_tasks]
        except Exception as e:
            logging.error(f"获取失败的任务失败: {str(e)}")
            return []

    def _calculate_queue_status(self, queue_id: str, total_tasks: int, completed_count: int, failed_count: int) -> str:
        """计算队列当前状态"""
        try:
            # 如果所有任务都完成或失败了
            if completed_count + failed_count >= total_tasks:
                return "completed"
                
            # 获取处理中的任务数
            processing_tasks = self.get_queue_tasks(queue_id)
            
            # 如果有任务正在处理
            if len(processing_tasks) > 0:
                return "processing"
                
            # 检查是否还有待处理的任务
            queue_key = f"{self.queue_prefix}{queue_id}"
            pending_tasks = self.redis.llen(queue_key)
            
            if pending_tasks > 0:
                return "waiting"
                
            # 如果没有待处理的任务，也没有处理中的任务，且有已完成的任务
            if completed_count > 0:
                return "completed"
                
            # 默认返回等待状态
            return "waiting"
            
        except Exception as e:
            logging.error(f"计算队列状态失败: {str(e)}")
            return "waiting"  # 发生错误时返回等待状态

    def get_user_active_queues(self, user_id: str) -> List[Dict]:
        """获取用户的所有活跃队列"""
        active_queues = []
        for key in self.redis.scan_iter(f"{self.queue_info_prefix}*"):
            # 修复解码问题
            key_str = key if isinstance(key, str) else key.decode('utf-8')
            queue_info = self.redis.hgetall(key_str)
            if queue_info.get("user_id") == user_id and queue_info.get("status") != "completed":
                queue_info["queue_id"] = key_str.split(":")[-1]
                active_queues.append(queue_info)
        return active_queues

    def cancel_queue(self, queue_id: str, user_id: str) -> bool:
        """取消队列"""
        queue_info_key = f"{self.queue_info_prefix}{queue_id}"
        queue_info = self.redis.hgetall(queue_info_key)
        
        if not queue_info or queue_info.get("user_id") != user_id:
            return False
            
        # 更新队列状态为已取消
        self.redis.hset(queue_info_key, "status", "cancelled")
        return True

    def update_queue_status(self, queue_id: str, status: str):
        """更新队列状态"""
        queue_info_key = f"{self.queue_info_prefix}{queue_id}"
        if self.redis.exists(queue_info_key):
            self.redis.hset(queue_info_key, "status", status)
            return True
        return False

    def get_all_active_queues(self) -> List[Dict]:
        """获取所有活跃队列"""
        active_queues = []
        
        # 扫描所有队列信息键
        for key in self.redis.scan_iter(f"{self.queue_info_prefix}*"):
            try:
                # 修复解码问题
                key_str = key if isinstance(key, str) else key.decode('utf-8')
                queue_info = self.redis.hgetall(key_str)
                if not queue_info:
                    continue
                    
                # 检查队列状态
                status = queue_info.get("status", "")
                if status not in ["completed", "cancelled", "failed"]:
                    # 提取队列ID
                    queue_id = key_str.split(':')[-1]
                    
                    # 添加到活跃队列列表
                    active_queues.append({
                        "queue_id": queue_id,
                        "status": status,
                        "user_id": queue_info.get("user_id", ""),
                        "created_at": queue_info.get("created_at", ""),
                        "total_tasks": int(queue_info.get("total_tasks", 0)),
                        "completed_tasks": int(queue_info.get("completed_tasks", 0)),
                        "failed_tasks": int(queue_info.get("failed_tasks", 0))
                    })
            except Exception as e:
                logging.error(f"处理队列信息失败: {e}")
            
        return active_queues

    def _cleanup_queue(self, queue_id: str):
        """清理已完成的队列相关数据"""
        try:
            # 删除队列相关的所有键
            keys_to_delete = [
                f"{self.queue_prefix}{queue_id}",
                f"{self.queue_info_prefix}{queue_id}",
                f"{self.queue_prefix}{queue_id}:completed_tasks",
                f"{self.queue_prefix}{queue_id}:failed_tasks",
                f"{self.queue_prefix}{queue_id}:processing_tasks"
            ]
            self.redis.delete(*keys_to_delete)
        except Exception as e:
            logging.error(f"清理队列 {queue_id} 失败: {str(e)}") 