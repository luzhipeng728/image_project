#!/usr/bin/env python
"""
测试脚本，用于检查worker状态和Redis中的任务情况
"""

import redis
import json
import os
import sys
from pprint import pprint

# 添加应用程序路径到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
        print(f"连接Redis失败: {e}")
        sys.exit(1)


def main():
    # 连接Redis
    r = get_redis_connection()

    # 打印Redis信息
    print("\n===== Redis信息 =====")
    info = r.info()
    print(f"Redis版本: {info.get('redis_version')}")
    print(f"已连接客户端数: {info.get('connected_clients')}")
    print(f"使用内存: {info.get('used_memory_human')}")

    # 检查图像生成队列
    print("\n===== 图像生成队列 =====")
    image_gen_keys = list(r.scan_iter("queue:image_generation_*:info"))
    print(f"找到 {len(image_gen_keys)} 个图像生成队列")

    for key in image_gen_keys:
        key_str = key.decode('utf-8')
        queue_data = r.get(key_str)
        if queue_data:
            try:
                queue_info = json.loads(queue_data)
                print(f"\n队列: {key_str}")
                print(f"  总任务数: {queue_info.get('total_tasks', 0)}")
                print(f"  已完成: {queue_info.get('total_completed', 0)}")
                print(f"  失败: {queue_info.get('total_failed', 0)}")
                print(f"  状态: {queue_info.get('status', 'unknown')}")

                # 检查任务数据
                queue_id = key_str.split(':')[1]
                task_keys = list(r.scan_iter(f"queue:{queue_id}:task:*"))
                print(f"  待处理任务数: {len(task_keys)}")

                # 检查队列中的任务
                tasks_key = f"queue:{queue_id}:tasks"
                tasks_data = r.lrange(tasks_key, 0, -1)
                if tasks_data:
                    print(f"  队列中的任务ID:")
                    for task_id in tasks_data:
                        print(f"    - {task_id.decode('utf-8')}")
            except Exception as e:
                print(f"  解析队列信息失败: {e}")

    # 检查RQ队列状态
    print("\n===== RQ队列状态 =====")
    rq_queues = list(r.smembers("rq:queues"))
    print(f"找到 {len(rq_queues)} 个RQ队列")

    for q in rq_queues:
        q_name = q.decode('utf-8')
        print(f"\n队列: {q_name}")

        # 检查队列中的作业
        jobs = r.lrange(f"rq:queue:{q_name}", 0, -1)
        print(f"  排队作业数: {len(jobs)}")

        # 检查作业细节
        if jobs and len(jobs) > 0:
            print("  前3个作业详情:")
            for i, job_id in enumerate(jobs[:3]):
                job_id_str = job_id.decode('utf-8')
                job_data = r.hgetall(f"rq:job:{job_id_str}")

                status = "未知"
                if job_data:
                    if b'status' in job_data:
                        status = job_data[b'status'].decode('utf-8')

                    print(f"    作业 {i+1}: {job_id_str} (状态: {status})")

                    if b'data' in job_data:
                        try:
                            data = json.loads(
                                job_data[b'data'].decode('utf-8'))
                            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                                task_data = data[0]
                                if 'image_id' in task_data:
                                    print(
                                        f"      图像ID: {task_data.get('image_id')}")
                                if 'prompt' in task_data:
                                    print(
                                        f"      提示词: {task_data.get('prompt')[:50]}...")
                                if 'model_id' in task_data:
                                    print(
                                        f"      模型ID: {task_data.get('model_id')}")
                        except:
                            pass

    # 检查已注册的workers
    print("\n===== 已注册Workers =====")
    workers = list(r.scan_iter("rq:worker:*"))
    print(f"找到 {len(workers)} 个注册的workers")

    for w in workers:
        w_name = w.decode('utf-8')
        print(f"\nWorker: {w_name}")

        # 检查worker状态
        w_data = r.hgetall(w_name)
        if b'queues' in w_data:
            queues = w_data[b'queues'].decode('utf-8')
            print(f"  监听队列: {queues}")
        if b'current_job' in w_data:
            current_job = w_data[b'current_job'].decode('utf-8')
            print(f"  当前作业: {current_job}")
        if b'last_heartbeat' in w_data:
            last_heartbeat = w_data[b'last_heartbeat'].decode('utf-8')
            print(f"  上次心跳: {last_heartbeat}")

    print("\n===== 完成 =====")


if __name__ == "__main__":
    main()
