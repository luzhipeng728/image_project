import asyncio
import hashlib
import logging
import random
import uuid
from app.database.database import get_db
import json
import sys
import os
from PIL import Image
from fastapi import HTTPException
from app.schemas.schemas import ImageToImageRequest
from app.services.image_service import ImageService
from app.core.config import settings
import redis
import datetime
import time
import functools
import concurrent.futures

def get_redis():
    """获取Redis连接"""
    return redis.Redis(
        host='localhost',
        port=6379,
        db=0,
        decode_responses=True
    )

# 修复关键点：使用线程池处理阻塞操作
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=10)

def run_in_threadpool(func):
    """将可能阻塞的同步操作包装到线程池中执行的装饰器"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.get_event_loop().run_in_executor(
            thread_pool, 
            functools.partial(func, *args, **kwargs)
        )
    return wrapper

# 将同步的数据库操作包装成异步
@run_in_threadpool
def get_project_info(project_id):
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("SELECT name, owner_id FROM projects WHERE id = ?", (project_id,))
        return cursor.fetchone()

@run_in_threadpool
def get_source_image_id(image_url):
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute('SELECT id FROM images WHERE file_path = ?', (image_url,))
        source_image = cursor.fetchone()
        return source_image['id'] if source_image else None

@run_in_threadpool
def open_and_resize_image(image_url):
    image = Image.open(image_url)
    original_width, original_height = image.size
    
    # 计算等比缩放后的尺寸
    max_size = 1024
    if original_width > max_size or original_height > max_size:
        if original_width >= original_height:
            ratio = max_size / original_width
            width = max_size
            height = int(original_height * ratio)
        else:
            ratio = max_size / original_height
            height = max_size
            width = int(original_width * ratio)
    else:
        if original_width >= original_height:
            ratio = max_size / original_width
            width = max_size
            height = int(original_height * ratio)
        else:
            ratio = max_size / original_height
            height = max_size
            width = int(original_width * ratio)
    
    return width, height

async def generate_from_image_json(image_url: str, prompt: str, model_id: str, project_id: str):
    """从已有图片生成新图片 (JSON请求版本)"""
    try:
        # 将所有可能阻塞的操作改为异步
        project_info = await get_project_info(project_id)
        if not project_info:
            raise HTTPException(status_code=404, detail={"message": "项目不存在"})
        
        project_name, owner_id = project_info
            
        # 异步处理图片尺寸
        try:
            width, height = await open_and_resize_image(image_url)
        except Exception as e:
            raise HTTPException(status_code=400, detail={
                "message": f"无法处理图片: {str(e)}"
            })

        # 异步获取源图片ID
        source_image_id = await get_source_image_id(image_url)
        if not source_image_id:
            raise HTTPException(status_code=404, detail={
                                "message": "源图片记录不存在"})

        # 检查缓存
        seed = random.randint(0, 1000000)
        cache_key = hashlib.md5(
            f"{image_url}_{prompt}_{seed}".encode()).hexdigest()
        cached_prompt = await ImageService.get_cached_image_description(image_url, prompt, seed)

        if cached_prompt:
            enhanced_prompt = cached_prompt
        else:
            # 调用LLM生成图片描述
            try:
                enhanced_prompt = await ImageService._call_llm_for_description(
                    image_url,
                    prompt,
                    seed
                )
                print(f"enhanced_prompt: {enhanced_prompt}")
                # 保存到缓存
                await ImageService.save_image_description_cache(
                    image_url=image_url,
                    original_prompt=prompt,
                    gen_seed=seed,
                    enhanced_prompt=enhanced_prompt,
                    width=width,
                    height=height
                )
            except Exception as e:
                logging.error(f"获取图片描述失败: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail={
                                    "message": f"获取图片描述失败: {str(e)}"})

        # 生成图片
        try:
            result_path = await ImageService.generate_image(
                username=owner_id,
                prompt=enhanced_prompt,
                model_id=model_id,
                seed=seed,
                width=width,
                height=height,
                enhance=False,
                source_image_id=source_image_id,
                generation_type='image_to_image',
                project_id=project_id
            )

            # 返回生成的图片URL
            image_url = settings.BACKEND_URL + '/' + result_path
            return {"id": uuid.uuid4(), "status": "completed", "image_url": image_url, "prompt": enhanced_prompt}
        except HTTPException as e:
            print(e)
    except Exception as e:
        print(e)


async def worker():
    print("Worker started")
    # 外部传参
    project_id = int(sys.argv[1])
    
    # 验证project_id
    if project_id <= 0:
        print(f"错误：项目ID必须是正整数，当前值: {project_id}")
        sys.exit(1)
    
    prompt = sys.argv[2] if len(sys.argv) > 2 else "根据图片给出详细的描述"
    model_id = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    # 获取所有未完成的任务 - 使用异步方式
    @run_in_threadpool
    def get_pending_tasks(project_id):
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM images WHERE is_generated = 0 AND project_id = ?", (project_id,))
        tasks = cursor.fetchall()
        # 将Row对象转换为字典列表
        task_list = [dict(task) for task in tasks]
        cursor.close()
        db.close()
        return task_list
    
    # 异步获取任务
    task_list = await get_pending_tasks(project_id)
    
    # 重置项目统计信息
    redis_client = get_redis()
    project_stats_key = f"project:{project_id}:stats"
    redis_client.hset(project_stats_key, mapping={
        "total_tasks": len(task_list),
        "completed_tasks": 0,
        "updated_at": datetime.datetime.now().isoformat()
    })
    print(f"已重置项目 {project_id} 统计数据: 当前活跃任务数 {len(task_list)}")
    
    # 创建信号量限制最大并发数
    semaphore = asyncio.Semaphore(9)
    
    # 包装generate_from_image_json函数以更新Redis状态
    async def process_subtask(task_data, subtask_index):
        async with semaphore:  # 信号量控制子任务级别的并发
            task_id = task_data['id']
            redis_key = f"project:{project_id}:task:{task_id}"
            subtask_key = f"{redis_key}:subtask:{subtask_index}"
            
            try:
                # 更新为处理中状态
                redis_client.hset(subtask_key, mapping={
                    "status": "processing",
                    "started_at": datetime.datetime.now().isoformat()
                })
                print(f"开始处理子任务 {task_id}_{subtask_index}")
                
                # 调用图片生成功能
                result = await generate_from_image_json(
                    task_data['file_path'], 
                    prompt, 
                    model_id, 
                    project_id
                )
                
                # 更新子任务状态
                redis_client.hset(subtask_key, mapping={
                    "status": "completed",
                    "completed_at": datetime.datetime.now().isoformat()
                })
                
                # 更新总进度
                redis_client.hincrby(redis_key, "completed", 1)
                completed = int(redis_client.hget(redis_key, "completed"))
                total = int(redis_client.hget(redis_key, "total"))
                
                print(f"子任务 {task_id}_{subtask_index} 完成，总进度: {completed}/{total}")
                
                # 检查任务是否全部完成
                if completed >= total:
                    redis_client.hset(redis_key, mapping={
                        "status": "completed",
                        "completed_at": datetime.datetime.now().isoformat()
                    })
                    
                    # 更新项目统计
                    redis_client.hincrby(project_stats_key, "completed_tasks", 1)
                    
                    # 获取项目进度
                    project_stats = redis_client.hgetall(project_stats_key)
                    project_total = int(project_stats.get("total_tasks", 0))
                    project_completed = int(project_stats.get("completed_tasks", 0))
                    
                    print(f"任务 {redis_key} 全部完成!")
                    print(f"项目 {project_id} 进度: {project_completed}/{project_total}")
                
                return result
            except Exception as e:
                # 更新失败状态
                redis_client.hset(subtask_key, mapping={
                    "status": "failed",
                    "error": str(e),
                    "failed_at": datetime.datetime.now().isoformat()
                })
                print(f"子任务 {task_id}_{subtask_index} 失败: {str(e)}")
                raise e
    
    async def process_task(task_data):
        # 创建任务记录
        task_id = task_data['id']
        total_subtasks = 3
        redis_key = f"project:{project_id}:task:{task_id}"

        # 检查任务是否已存在并设置状态
        task_exists = redis_client.exists(redis_key)
        if task_exists:
            status = redis_client.hget(redis_key, "status")
            if status == "completed":
                # 删除旧任务并创建新任务
                for i in range(int(redis_client.hget(redis_key, "total") or total_subtasks)):
                    subtask_key = f"{redis_key}:subtask:{i}"
                    if redis_client.exists(subtask_key):
                        redis_client.delete(subtask_key)
                redis_client.delete(redis_key)
                
        # 创建/更新任务
        redis_client.hset(redis_key, mapping={
            "total": total_subtasks,
            "completed": 0,
            "status": "processing",
            "created_at": datetime.datetime.now().isoformat()
        })
                
        # 收集所有子任务
        sub_tasks = []
        for i in range(total_subtasks):
            subtask_key = f"{redis_key}:subtask:{i}"
            
            # 创建子任务记录
            redis_client.hset(subtask_key, mapping={
                "id": f"{task_id}_{i}",
                "status": "pending",
                "updated_at": datetime.datetime.now().isoformat()
            })
            
            # 添加子任务处理
            sub_tasks.append(process_subtask(task_data, i))
        
        # 使用gather并发执行子任务 - 关键点：确保真正的并发
        results = await asyncio.gather(*sub_tasks, return_exceptions=True)
        return results
    
    # 为所有任务创建协程
    all_tasks = [process_task(task) for task in task_list]
    
    # JSON序列化函数
    def json_serializable(obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    
    # 并发执行所有任务
    all_results = await asyncio.gather(*all_tasks, return_exceptions=True)
    
    # 打印结果
    for task, results in zip(task_list, all_results):
        print(f"任务 {task['id']} 完成，结果：")
        try:
            print(json.dumps({**task, "results": results}, indent=4, default=json_serializable))
        except:
            print(f"结果无法序列化: {results}")
    
    print("所有任务处理完成")
    
    # 关闭线程池
    thread_pool.shutdown()


def check_project_has_running_task(project_id):
    """检查项目是否有正在运行的任务"""
    redis_client = get_redis()
    project_stats_key = f"project:{project_id}:stats"
    
    # 检查项目统计是否存在
    if not redis_client.exists(project_stats_key):
        return False
    
    # 从Redis获取项目状态
    stats = redis_client.hgetall(project_stats_key)
    total_tasks = int(stats.get("total_tasks", 0))
    completed_tasks = int(stats.get("completed_tasks", 0))
    
    # 检查活跃任务
    if total_tasks > completed_tasks:
        for key in redis_client.scan_iter(f"project:{project_id}:task:*"):
            if redis_client.type(key) == "hash" and not ":subtask:" in key:
                status = redis_client.hget(key, "status")
                if status == "processing":
                    return True
    
    return False


def clear_project_redis_data(project_id):
    """清理项目相关的所有Redis数据"""
    redis_client = get_redis()
    project_keys = redis_client.keys(f"project:{project_id}:*")
    if project_keys:
        redis_client.delete(*project_keys)
    print(f"已清理项目 {project_id} 的所有Redis数据")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python worker.py [project_id] [prompt] [model_id]")
        sys.exit(1)

    # 如果是删除任务，则删除任务
    if len(sys.argv) > 2 and sys.argv[2] == "delete":
        clear_project_redis_data(sys.argv[1])
        sys.exit(0)
        
    project_id = int(sys.argv[1])
    
    # 检查项目是否有正在运行的任务
    if check_project_has_running_task(project_id):
        print(f"项目 {project_id} 已有任务正在运行，请等待当前任务完成后再运行新任务")
        sys.exit(0)  # 直接退出程序，返回成功状态码
    
    # 继续处理
    prompt = sys.argv[2] if len(sys.argv) > 2 else "根据图片给出详细的描述"
    model_id = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    # 启动worker处理任务
    asyncio.run(worker())