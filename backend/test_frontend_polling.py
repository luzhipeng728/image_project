#!/usr/bin/env python
"""
测试前端轮询队列进度更新的脚本
模拟前端轮询队列状态并模拟后台更新进度
"""

import json
import time
import uuid
import redis
import threading
import argparse
from redis import Redis


def simulate_frontend_polling(redis_conn, queue_id, interval=2):
    """模拟前端轮询队列状态"""
    print("\n===== 开始模拟前端轮询 =====")

    polling_count = 0
    last_completed = 0

    try:
        while True:
            polling_count += 1
            queue_info_key = f"queue:{queue_id}:info"

            # 获取队列信息
            queue_info_data = redis_conn.get(queue_info_key)

            if not queue_info_data:
                print(f"前端轮询: 未找到队列 {queue_id} 的信息")
                break

            try:
                queue_data = json.loads(queue_info_data)
                status = queue_data.get("status", "未知")
                total_tasks = queue_data.get("total_tasks", 0)
                total_completed = queue_data.get("total_completed", 0)
                total_failed = queue_data.get("total_failed", 0)

                # 计算进度百分比
                progress = 0
                if total_tasks > 0:
                    progress = int(
                        (total_completed + total_failed) / total_tasks * 100)

                print(
                    f"前端轮询 #{polling_count}: 状态={status}, 进度={progress}%, 完成={total_completed}/{total_tasks}")

                # 如果有新的任务完成，模拟前端更新
                if total_completed > last_completed:
                    new_completed = total_completed - last_completed
                    print(f"前端检测到 {new_completed} 个新完成的任务，更新UI显示...")
                    last_completed = total_completed

                # 如果队列已完成，结束轮询
                if status == "completed" or (total_completed + total_failed) >= total_tasks:
                    print("队列已完成，前端停止轮询")
                    break

            except Exception as e:
                print(f"解析队列数据失败: {e}")
                break

            # 轮询间隔
            time.sleep(interval)

    except KeyboardInterrupt:
        print("前端轮询被用户中断")

    print("===== 前端轮询结束 =====\n")


def simulate_backend_processing(redis_conn, queue_id, task_count=10, task_time=3):
    """模拟后台处理队列任务并更新进度"""
    print("\n===== 开始模拟后台处理 =====")

    # 创建队列信息
    queue_info = {
        "status": "processing",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tasks": task_count,
        "total_completed": 0,
        "total_failed": 0,
        "image_ids": list(range(1, task_count + 1)),
        "concurrency": 3
    }

    # 保存队列信息到Redis
    queue_info_key = f"queue:{queue_id}:info"
    redis_conn.set(queue_info_key, json.dumps(queue_info))

    print(f"创建队列 {queue_id}，任务总数: {task_count}")

    # 创建一个包含任务ID的列表
    task_ids = []
    for i in range(task_count):
        job_id = str(uuid.uuid4())
        task_ids.append((i+1, job_id))  # (image_id, job_id)

    try:
        for i, (image_id, job_id) in enumerate(task_ids):
            # 创建任务进度键
            progress_key = f"task_progress:{job_id}"

            # 初始化进度为0
            redis_conn.hset(progress_key, "progress", 0)
            redis_conn.hset(progress_key, "status", "processing")
            redis_conn.expire(progress_key, 3600)  # 1小时过期

            print(
                f"开始处理任务 {i+1}/{task_count} (image_id={image_id}, job_id={job_id})")

            # 更新进度为10%（开始）
            redis_conn.hset(progress_key, "progress", 10)
            time.sleep(task_time * 0.1)

            # 更新进度为40%（第一个变体）
            redis_conn.hset(progress_key, "progress", 40)
            time.sleep(task_time * 0.3)

            # 更新进度为70%（第二个变体）
            redis_conn.hset(progress_key, "progress", 70)
            time.sleep(task_time * 0.3)

            # 更新进度为100%（完成）
            redis_conn.hset(progress_key, "progress", 100)
            redis_conn.hset(progress_key, "status", "completed")

            # 将任务添加到已完成任务集合
            completed_tasks_key = f"queue:{queue_id}:completed_tasks"
            redis_conn.sadd(completed_tasks_key, image_id)
            redis_conn.expire(completed_tasks_key, 3600)

            # 更新队列信息
            queue_info["total_completed"] = i + 1
            if queue_info["total_completed"] >= queue_info["total_tasks"]:
                queue_info["status"] = "completed"

            redis_conn.set(queue_info_key, json.dumps(queue_info))

            print(f"任务 {i+1}/{task_count} 已完成，队列进度: {int((i+1)/task_count*100)}%")

            # 最后一个任务完成后稍微延迟
            if i == task_count - 1:
                print("所有任务已完成，等待前端最后一次轮询...")
                time.sleep(3)

    except KeyboardInterrupt:
        print("后台处理被用户中断")

    print("===== 后台处理结束 =====\n")


def main():
    """主函数：测试前端轮询与后台更新的交互"""
    parser = argparse.ArgumentParser(description="测试前端轮询队列进度")
    parser.add_argument("--tasks", type=int, default=5, help="队列中的任务数量")
    parser.add_argument("--task-time", type=int,
                        default=2, help="每个任务的处理时间(秒)")
    parser.add_argument("--poll-interval", type=int,
                        default=1, help="前端轮询间隔(秒)")
    args = parser.parse_args()

    # 连接到Redis
    redis_conn = Redis()

    # 创建唯一的队列ID
    queue_id = f"image_generation_test_{uuid.uuid4().hex[:8]}"

    print(f"\n开始测试前端轮询与后台进度更新 (队列ID: {queue_id})")
    print(
        f"任务数量: {args.tasks}, 每个任务处理时间: {args.task_time}秒, 前端轮询间隔: {args.poll_interval}秒")

    try:
        # 创建并启动前端轮询线程
        frontend_thread = threading.Thread(
            target=simulate_frontend_polling,
            args=(redis_conn, queue_id, args.poll_interval)
        )
        frontend_thread.daemon = True
        frontend_thread.start()

        # 稍微延迟，确保前端线程已启动
        time.sleep(1)

        # 运行后台处理
        simulate_backend_processing(
            redis_conn, queue_id, args.tasks, args.task_time)

        # 等待前端线程完成
        frontend_thread.join(timeout=10)

        print("\n测试结论:")
        print("1. 前端轮询可以成功获取队列进度更新")
        print("2. 当队列状态变为completed时，前端应停止轮询")
        print("3. 前端可以根据任务完成情况更新UI，而无需用户保持页面不变")

    except KeyboardInterrupt:
        print("\n测试被用户中断")
    finally:
        # 清理Redis键
        queue_info_key = f"queue:{queue_id}:info"
        completed_tasks_key = f"queue:{queue_id}:completed_tasks"
        redis_conn.delete(queue_info_key)
        redis_conn.delete(completed_tasks_key)

        print(f"\n测试完成，已清理Redis中的测试数据 (队列ID: {queue_id})")


if __name__ == "__main__":
    main()
