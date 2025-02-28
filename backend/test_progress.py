#!/usr/bin/env python
"""
测试后台任务进度更新功能
"""
import time
import json
import uuid
import redis
from redis import Redis
import argparse


def main():
    """主函数：测试后台任务进度更新"""
    parser = argparse.ArgumentParser(description="测试任务进度更新")
    parser.add_argument("--duration", type=int, default=30, help="模拟任务持续时间(秒)")
    args = parser.parse_args()

    # 连接到Redis
    redis_conn = Redis()

    # 创建唯一的任务ID
    job_id = str(uuid.uuid4())
    queue_id = f"image_generation_test_{job_id[:8]}"

    print(f"创建测试任务，ID: {job_id}")

    # 创建队列信息
    queue_info = {
        "status": "processing",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tasks": 3,  # 模拟3个任务
        "total_completed": 0,
        "total_failed": 0,
        "image_ids": [1, 2, 3],
        "concurrency": 3
    }

    # 保存队列信息到Redis
    queue_info_key = f"queue:{queue_id}:info"
    redis_conn.set(queue_info_key, json.dumps(queue_info))

    # 创建任务进度键
    progress_key = f"task_progress:{job_id}"

    # 初始化进度为0
    redis_conn.hset(progress_key, "progress", 0)
    redis_conn.hset(progress_key, "status", "processing")

    # 监控任务进度
    def monitor_progress():
        """监控任务进度"""
        while True:
            progress = redis_conn.hget(progress_key, "progress")
            status = redis_conn.hget(progress_key, "status")

            if progress:
                progress = int(progress)
                status = status.decode('utf-8') if status else "未知"

                # 获取队列信息
                queue_info_data = redis_conn.get(queue_info_key)
                queue_status = "未知"
                completed = 0
                failed = 0

                if queue_info_data:
                    try:
                        queue_data = json.loads(queue_info_data)
                        queue_status = queue_data.get("status", "未知")
                        completed = queue_data.get("total_completed", 0)
                        failed = queue_data.get("total_failed", 0)
                    except Exception as e:
                        print(f"解析队列数据失败: {e}")

                print(f"任务进度: {progress}%, 状态: {status}")
                print(f"队列状态: {queue_status}, 已完成: {completed}, 失败: {failed}")

                if status in ["completed", "failed"] and progress >= 100:
                    print(f"任务已{status}，测试结束")
                    break

            time.sleep(1)

    # 启动监控线程
    import threading
    monitor_thread = threading.Thread(target=monitor_progress)
    monitor_thread.daemon = True
    monitor_thread.start()

    try:
        # 模拟任务执行过程中的进度更新
        duration = args.duration

        # 设置开始进度为10%
        print("模拟任务开始，设置进度为10%")
        redis_conn.hset(progress_key, "progress", 10)
        time.sleep(duration * 0.1)

        # 模拟第一个任务完成，进度40%
        print("模拟第一个任务完成，设置进度为40%")
        redis_conn.hset(progress_key, "progress", 40)

        # 更新队列状态
        queue_info["total_completed"] = 1
        redis_conn.set(queue_info_key, json.dumps(queue_info))
        time.sleep(duration * 0.3)

        # 模拟第二个任务完成，进度70%
        print("模拟第二个任务完成，设置进度为70%")
        redis_conn.hset(progress_key, "progress", 70)

        # 更新队列状态
        queue_info["total_completed"] = 2
        redis_conn.set(queue_info_key, json.dumps(queue_info))
        time.sleep(duration * 0.3)

        # 模拟任务全部完成，进度100%
        print("模拟所有任务完成，设置进度为100%")
        redis_conn.hset(progress_key, "progress", 100)
        redis_conn.hset(progress_key, "status", "completed")

        # 更新队列状态
        queue_info["total_completed"] = 3
        queue_info["status"] = "completed"
        redis_conn.set(queue_info_key, json.dumps(queue_info))

        # 等待监控线程完成
        monitor_thread.join(5)

        print(f"测试完成: 任务 {job_id} 已成功模拟进度更新")

    except KeyboardInterrupt:
        print("测试被用户中断")
    finally:
        # 清理Redis键
        redis_conn.delete(progress_key)
        redis_conn.delete(queue_info_key)


if __name__ == "__main__":
    main()
