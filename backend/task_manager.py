import redis
import datetime
import json
import time

def get_redis():
    """获取Redis连接"""
    return redis.Redis(
        host='localhost',
        port=6379,
        db=0,
        decode_responses=True
    )

class TaskManager:
    """任务管理器，处理Redis中的任务状态"""
    
    def __init__(self, project_id):
        self.redis = get_redis()
        self.project_id = project_id
        self.project_stats_key = f"project:{project_id}:stats"
        self.active_tasks_key = f"project:{project_id}:active_tasks"  # 新增：活跃任务集合
        self.task_prefix = f"project:{project_id}:task:"
        
    def register_active_task(self, task_id):
        """将任务添加到活跃任务集合"""
        self.redis.sadd(self.active_tasks_key, task_id)
        # 为活跃任务集合设置一个较长的过期时间（比如7天）以防止长期累积
        self.redis.expire(self.active_tasks_key, 60*60*24*7)  # 7天过期
        
    def remove_active_task(self, task_id):
        """从活跃任务集合中移除任务"""
        self.redis.srem(self.active_tasks_key, task_id)
        
    def get_active_tasks(self):
        """获取当前所有活跃任务ID"""
        return self.redis.smembers(self.active_tasks_key)
    
    def create_task(self, task_id, total_subtasks=3):
        """创建新任务记录"""
        task_key = f"{self.task_prefix}{task_id}"
        
        # 检查任务是否已存在
        task_exists = self.redis.exists(task_key)
        status = None
        
        if task_exists:
            status = self.redis.hget(task_key, "status")
            # 如果任务已完成，删除旧记录
            if status == "completed":
                # 删除子任务
                for i in range(int(self.redis.hget(task_key, "total"))):
                    subtask_key = f"{task_key}:subtask:{i}"
                    if self.redis.exists(subtask_key):
                        self.redis.delete(subtask_key)
                # 删除主任务
                self.redis.delete(task_key)
        
        # 创建新任务（或覆盖未完成的旧任务）
        self.redis.hset(task_key, mapping={
            "total": total_subtasks,
            "completed": 0,
            "status": "processing",
            "created_at": datetime.datetime.now().isoformat(),
            "session_id": int(time.time())  # 添加会话ID标识这次运行
        })
        
        # 注册为活跃任务
        self.register_active_task(task_id)
        
        # 更新项目统计
        if not task_exists or status != "completed":
            # 确保项目统计存在
            if not self.redis.exists(self.project_stats_key):
                self.redis.hset(self.project_stats_key, mapping={
                    "total_tasks": 0,
                    "completed_tasks": 0,
                    "started_at": datetime.datetime.now().isoformat(),
                    "session_id": int(time.time())  # 添加会话ID
                })
            self.redis.hincrby(self.project_stats_key, "total_tasks", 1)
            
        return task_key
        
    def create_subtask(self, task_id, subtask_index):
        """创建子任务记录"""
        task_key = f"{self.task_prefix}{task_id}"
        subtask_key = f"{task_key}:subtask:{subtask_index}"
        subtask_id = f"{task_id}_{subtask_index}"
        
        # 检查子任务状态
        subtask_status = "pending"
        if self.redis.exists(subtask_key):
            subtask_status = self.redis.hget(subtask_key, "status")
        
        # 如果任务不是completed状态但子任务已完成，跳过
        if subtask_status == "completed" and self.redis.hget(task_key, "status") != "completed":
            return None
            
        # 创建/更新子任务
        self.redis.hset(subtask_key, mapping={
            "id": subtask_id,
            "status": "pending",
            "updated_at": datetime.datetime.now().isoformat(),
            "session_id": int(time.time())  # 添加会话ID
        })
        
        return subtask_key
    
    def update_subtask_status(self, task_id, subtask_index, status, error=None):
        """更新子任务状态"""
        task_key = f"{self.task_prefix}{task_id}"
        subtask_key = f"{task_key}:subtask:{subtask_index}"
        
        update_data = {
            "status": status,
            "updated_at": datetime.datetime.now().isoformat()
        }
        
        if status == "processing":
            update_data["started_at"] = datetime.datetime.now().isoformat()
        elif status == "completed":
            update_data["completed_at"] = datetime.datetime.now().isoformat()
            # 更新总进度
            self.redis.hincrby(task_key, "completed", 1)
            completed = int(self.redis.hget(task_key, "completed"))
            total = int(self.redis.hget(task_key, "total"))
            
            # 检查任务是否全部完成
            if completed >= total:
                self.redis.hset(task_key, mapping={
                    "status": "completed",
                    "completed_at": datetime.datetime.now().isoformat()
                })
                
                # 从活跃任务中移除
                self.remove_active_task(task_id)
                
                # 更新项目统计
                self.redis.hincrby(self.project_stats_key, "completed_tasks", 1)
        elif status == "failed":
            update_data["failed_at"] = datetime.datetime.now().isoformat()
            if error:
                update_data["error"] = error
        
        self.redis.hset(subtask_key, mapping=update_data)
        
    def clear_completed_tasks(self, older_than_hours=24):
        """清理已完成的任务（默认清理24小时前完成的任务）"""
        # 获取所有项目任务
        cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=older_than_hours)
        cutoff_str = cutoff_time.isoformat()
        
        # 查找所有已完成任务
        for key in self.redis.scan_iter(f"{self.task_prefix}*"):
            if ":subtask:" not in key and self.redis.type(key) == "hash":
                task_data = self.redis.hgetall(key)
                
                # 检查是否已完成且完成时间早于截止时间
                if (task_data.get("status") == "completed" and 
                    task_data.get("completed_at", "") < cutoff_str):
                    
                    task_id = key.split(":")[-1]
                    
                    # 删除子任务
                    for i in range(int(task_data.get("total", 0))):
                        subtask_key = f"{key}:subtask:{i}"
                        if self.redis.exists(subtask_key):
                            self.redis.delete(subtask_key)
                    
                    # 删除主任务
                    self.redis.delete(key)
                    print(f"已清理过期完成任务: {key}")
                    
                    # 从活跃任务集合中移除
                    self.remove_active_task(task_id)
    
    def get_current_session_tasks(self):
        """获取当前会话的所有任务"""
        current_session = self.redis.hget(self.project_stats_key, "session_id")
        if not current_session:
            return []
            
        session_tasks = []
        for task_id in self.get_active_tasks():
            task_key = f"{self.task_prefix}{task_id}"
            if self.redis.exists(task_key):
                task_session = self.redis.hget(task_key, "session_id")
                if task_session == current_session:
                    session_tasks.append(task_id)
        
        return session_tasks
    
    def reset_project_stats(self, active_tasks_count):
        """重置项目统计信息"""
        session_id = int(time.time())
        self.redis.hset(self.project_stats_key, mapping={
            "total_tasks": active_tasks_count,
            "completed_tasks": 0,
            "updated_at": datetime.datetime.now().isoformat(),
            "session_id": session_id
        })
        return session_id
                    
    def check_project_has_running_task(self):
        """检查项目是否有正在运行的任务"""
        # 检查项目统计是否存在
        if not self.redis.exists(self.project_stats_key):
            return False
        
        # 从Redis获取项目状态
        stats = self.redis.hgetall(self.project_stats_key)
        total_tasks = int(stats.get("total_tasks", 0))
        completed_tasks = int(stats.get("completed_tasks", 0))
        
        # 检查活跃任务
        if total_tasks > completed_tasks:
            # 只检查当前会话的活跃任务
            current_session = stats.get("session_id")
            if not current_session:
                return False
                
            for task_id in self.get_active_tasks():
                task_key = f"{self.task_prefix}{task_id}"
                if self.redis.exists(task_key):
                    # 验证任务属于当前会话
                    task_session = self.redis.hget(task_key, "session_id")
                    if task_session == current_session:
                        status = self.redis.hget(task_key, "status")
                        if status == "processing":
                            return True
        
        return False
        
    def clear_all_project_data(self):
        """清理项目相关的所有Redis数据"""
        project_keys = self.redis.keys(f"project:{self.project_id}:*")
        if project_keys:
            self.redis.delete(*project_keys)
        print(f"已清理项目 {self.project_id} 的所有Redis数据")