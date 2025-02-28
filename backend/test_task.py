#!/usr/bin/env python
import time
import redis
from redis import Redis

# 连接到Redis
redis_conn = Redis()


def test_task(job_id, duration=10):
    """模拟一个长时间运行的任务，并在Redis中更新进度"""
    print(f"开始执行任务 {job_id}")

    # 初始化进度为0
    redis_conn.hset(f"task_progress:{job_id}", "progress", 0)
    redis_conn.hset(f"task_progress:{job_id}", "status", "processing")

    # 模拟任务执行过程中的进度更新
    for i in range(1, 11):
        time.sleep(duration / 10)
        progress = i * 10
        print(f"任务 {job_id} 进度: {progress}%")
        redis_conn.hset(f"task_progress:{job_id}", "progress", progress)

    # 完成任务
    redis_conn.hset(f"task_progress:{job_id}", "status", "completed")
    print(f"任务 {job_id} 已完成")
    return f"任务 {job_id} 已完成"
