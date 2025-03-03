import requests
import base64
import json
import time
import os
from datetime import datetime, timedelta
import logging
from typing import Dict, Any, List, Optional, Tuple, Generator
import statistics

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("i2v_service.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("I2V-Service")


class TimeEstimator:
    """时间预估器，用于计算剩余时间"""

    def __init__(self, total_steps: int):
        """
        初始化时间预估器

        Args:
            total_steps: 总步数
        """
        self.total_steps = total_steps
        self.start_time = time.time()
        self.step_times = []  # 每步所需时间列表
        self.last_step_time = self.start_time  # 上一步的时间
        self.last_step = 0  # 上一步的步数

    def update(self, current_step: int) -> Dict[str, Any]:
        """
        更新进度并计算预估时间

        Args:
            current_step: 当前步数

        Returns:
            包含时间预估信息的字典
        """
        current_time = time.time()

        # 如果是同一步，不更新
        if current_step == self.last_step:
            elapsed_time = current_time - self.start_time

            # 计算预估剩余时间
            if len(self.step_times) > 0:
                avg_step_time = statistics.mean(self.step_times)
                remaining_steps = self.total_steps - current_step
                estimated_remaining_time = avg_step_time * remaining_steps
            else:
                estimated_remaining_time = 0

            return {
                "elapsed_seconds": round(elapsed_time, 1),
                "elapsed_formatted": str(timedelta(seconds=int(elapsed_time))),
                "estimated_remaining_seconds": round(estimated_remaining_time, 1),
                "estimated_remaining_formatted": str(timedelta(seconds=int(estimated_remaining_time))),
                "estimated_total_seconds": round(elapsed_time + estimated_remaining_time, 1),
                "estimated_total_formatted": str(timedelta(seconds=int(elapsed_time + estimated_remaining_time))),
                "steps_per_second": 0 if elapsed_time == 0 else round(current_step / elapsed_time, 2),
                "percent_complete": round((current_step / self.total_steps) * 100, 1) if self.total_steps > 0 else 0
            }

        # 计算这一步所需的时间
        step_time = current_time - self.last_step_time
        steps_taken = current_step - self.last_step

        # 如果是多步一起更新，计算平均每步时间
        if steps_taken > 1:
            avg_step_time = step_time / steps_taken
            self.step_times.extend([avg_step_time] * steps_taken)
        else:
            self.step_times.append(step_time)

        # 保留最近的10个步骤用于计算平均值
        if len(self.step_times) > 10:
            self.step_times = self.step_times[-10:]

        # 更新上一步信息
        self.last_step_time = current_time
        self.last_step = current_step

        # 计算已用时间
        elapsed_time = current_time - self.start_time

        # 计算预估剩余时间
        avg_step_time = statistics.mean(self.step_times)
        remaining_steps = self.total_steps - current_step
        estimated_remaining_time = avg_step_time * remaining_steps

        return {
            "elapsed_seconds": round(elapsed_time, 1),
            "elapsed_formatted": str(timedelta(seconds=int(elapsed_time))),
            "estimated_remaining_seconds": round(estimated_remaining_time, 1),
            "estimated_remaining_formatted": str(timedelta(seconds=int(estimated_remaining_time))),
            "estimated_total_seconds": round(elapsed_time + estimated_remaining_time, 1),
            "estimated_total_formatted": str(timedelta(seconds=int(elapsed_time + estimated_remaining_time))),
            "steps_per_second": round(current_step / elapsed_time, 2) if elapsed_time > 0 else 0,
            "percent_complete": round((current_step / self.total_steps) * 100, 1) if self.total_steps > 0 else 0,
            "current_step_seconds": round(step_time, 1),
            "average_step_seconds": round(avg_step_time, 3)
        }


class I2VService:
    """图像到视频(I2V)服务封装类"""

    def __init__(self, server_url: str = "http://localhost:9000/api/i2v/generate"):
        """
        初始化I2V服务

        Args:
            server_url: I2V服务器URL
        """
        self.server_url = server_url
        logger.info(f"I2V服务初始化，服务器地址: {server_url}")

        # 节点ID到中文描述的映射
        self.node_descriptions = {
            "11": "初始化服务",
            "13": "加载模型",
            "16": "准备环境",
            "17": "设置迭代参数",
            "18": "加载图像",
            "21": "预处理图像",
            "22": "配置模型参数",
            "23": "准备提示词",
            "24": "设置采样器",
            "25": "配置调度器",
            "26": "准备推理",
            "27": "视频生成推理",
            "28": "后处理帧",
            "29": "准备视频",
            "30": "拼接视频",
            "31": "优化视频",
            "32": "后处理视频",
            "40": "完成处理"
        }

    @staticmethod
    def image_to_base64(image_path: str) -> str:
        """
        将图片转换为base64编码

        Args:
            image_path: 图片路径

        Returns:
            base64编码的图片字符串
        """
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(
                image_file.read()).decode('utf-8')
        return encoded_string

    @staticmethod
    def image_data_to_base64(image_data: bytes) -> str:
        """
        将图片数据转换为base64编码

        Args:
            image_data: 图片二进制数据

        Returns:
            base64编码的图片字符串
        """
        return base64.b64encode(image_data).decode('utf-8')

    def generate_video(self,
                       image_path: Optional[str] = None,
                       image_data: Optional[bytes] = None,
                       image_base64: Optional[str] = None,
                       positive_prompt: str = "这个女孩开心的看着手机,并且非常激动",
                       steps: int = 10,
                       num_frames: int = 81,
                       stream: bool = True) -> Generator[Dict[str, Any], None, None]:
        """
        生成视频并返回事件流

        Args:
            image_path: 图片路径（三选一）
            image_data: 图片二进制数据（三选一）
            image_base64: 图片base64编码（三选一）
            positive_prompt: 正向提示词
            steps: 生成步数
            num_frames: 帧数
            stream: 是否以流的形式返回结果

        Returns:
            事件生成器，每个事件为一个字典
        """
        # 检查图片输入
        if image_path is None and image_data is None and image_base64 is None:
            raise ValueError("必须提供图片路径、图片数据或图片base64编码中的一个")

        # 获取base64编码的图片
        if image_base64 is not None:
            base64_str = image_base64
        elif image_path is not None:
            base64_str = self.image_to_base64(image_path)
        else:
            base64_str = self.image_data_to_base64(image_data)

        # 准备请求数据
        data = {
            "image_base64": base64_str,
            "positive_prompt": positive_prompt,
            "steps": steps,
            "num_frames": num_frames
        }

        logger.info(
            f"开始生成视频: prompt='{positive_prompt}', steps={steps}, frames={num_frames}")

        # 创建时间预估器
        inference_estimator = TimeEstimator(steps)  # 节点27的时间预估
        video_estimator = TimeEstimator(num_frames)  # 节点30的时间预估

        # 发送请求
        try:
            response = requests.post(
                self.server_url,
                json=data,
                stream=True,
                timeout=600,  # 10分钟超时
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                error_msg = f"请求失败，状态码: {response.status_code}, 响应: {response.text}"
                logger.error(error_msg)
                yield {
                    "event_type": "error",
                    "data": {
                        "message": error_msg,
                        "status_code": response.status_code
                    }
                }
                return

            logger.info("请求成功，开始接收响应")

            # 处理SSE流
            event_count = 0

            # 用于跟踪关键节点的状态
            status = {
                "load_image": False,  # 节点18
                "setup_params": False,  # 节点17
                "inference": False,  # 节点27
                "inference_progress": 0,  # 节点27的进度
                "inference_time_estimate": None,  # 节点27的时间预估
                "video_combine": False,  # 节点30
                "video_progress": 0,  # 节点30的进度
                "video_time_estimate": None,  # 节点30的时间预估
                "completed": False,
                "video_path": None,
                "error": None,
                "total_time_estimate": {
                    "elapsed_seconds": 0,
                    "estimated_remaining_seconds": 0,
                    "estimated_total_seconds": 0
                }
            }

            # 记录开始时间
            start_time = time.time()

            for line in response.iter_lines():
                if line:
                    # 解析SSE数据行
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data_str = line[6:]  # 去掉 'data: ' 前缀
                        try:
                            data_json = json.loads(data_str)
                            event_count += 1

                            # 获取事件类型和数据
                            event_type = data_json.get('type', 'unknown')
                            event_data = data_json.get('data', {})

                            # 处理不同类型的事件
                            if event_type == "executing":
                                node_id = event_data.get('node')
                                node_desc = self.node_descriptions.get(
                                    node_id, "")

                                if node_id == "18":
                                    status["load_image"] = True
                                    logger.info(f"开始加载图像 ({node_desc})")
                                elif node_id == "17":
                                    status["setup_params"] = True
                                    logger.info(f"开始设置迭代参数 ({node_desc})")
                                elif node_id == "27":
                                    status["inference"] = True
                                    logger.info(f"开始视频生成推理 ({node_desc})")
                                elif node_id == "30":
                                    status["video_combine"] = True
                                    logger.info(f"开始拼接视频 ({node_desc})")

                            elif event_type == "progress":
                                node_id = event_data.get('node')
                                value = event_data.get('value', 0)
                                max_val = event_data.get('max', 100)
                                percentage = int((value / max_val) * 100)

                                # 获取节点描述
                                node_desc = self.node_descriptions.get(
                                    node_id, "")

                                if node_id == "27":
                                    status["inference_progress"] = percentage
                                    # 更新推理时间预估
                                    status["inference_time_estimate"] = inference_estimator.update(
                                        value)
                                    logger.info(
                                        f"视频生成进度: {percentage}%, 预计剩余: {status['inference_time_estimate']['estimated_remaining_formatted']} ({node_desc})")
                                elif node_id == "30":
                                    status["video_progress"] = percentage
                                    # 更新视频拼接时间预估
                                    status["video_time_estimate"] = video_estimator.update(
                                        value)
                                    logger.info(
                                        f"视频拼接进度: {percentage}%, 预计剩余: {status['video_time_estimate']['estimated_remaining_formatted']} ({node_desc})")

                                # 计算总体时间预估
                                current_time = time.time()
                                elapsed_time = current_time - start_time

                                # 如果两个阶段都有预估，计算总预估时间
                                if status["inference_time_estimate"] and not status["video_time_estimate"]:
                                    # 只有推理阶段的预估
                                    remaining_time = status["inference_time_estimate"]["estimated_remaining_seconds"]
                                    # 假设视频拼接阶段大约需要推理阶段的1/3时间
                                    remaining_time += (
                                        status["inference_time_estimate"]["estimated_total_seconds"] / 3)
                                elif status["video_time_estimate"]:
                                    # 已经到了视频拼接阶段
                                    remaining_time = status["video_time_estimate"]["estimated_remaining_seconds"]
                                else:
                                    # 还没有足够信息进行预估
                                    remaining_time = 0

                                status["total_time_estimate"] = {
                                    "elapsed_seconds": round(elapsed_time, 1),
                                    "elapsed_formatted": str(timedelta(seconds=int(elapsed_time))),
                                    "estimated_remaining_seconds": round(remaining_time, 1),
                                    "estimated_remaining_formatted": str(timedelta(seconds=int(remaining_time))),
                                    "estimated_total_seconds": round(elapsed_time + remaining_time, 1),
                                    "estimated_total_formatted": str(timedelta(seconds=int(elapsed_time + remaining_time))),
                                    "percent_complete": round(((status["inference_progress"] * 0.7) + (status["video_progress"] * 0.3)), 1)
                                }

                            elif event_type == "executed":
                                node_id = event_data.get('node')
                                node_desc = self.node_descriptions.get(
                                    node_id, "")
                                if node_id == "30" and 'output' in event_data and 'gifs' in event_data['output']:
                                    for gif in event_data['output']['gifs']:
                                        status["video_path"] = gif.get(
                                            'fullpath')
                                        logger.info(
                                            f"视频生成完成: {status['video_path']} ({node_desc})")

                            elif event_type == "execution_success":
                                status["completed"] = True
                                # 更新总时间
                                current_time = time.time()
                                elapsed_time = current_time - start_time
                                status["total_time_estimate"]["elapsed_seconds"] = round(
                                    elapsed_time, 1)
                                status["total_time_estimate"]["elapsed_formatted"] = str(
                                    timedelta(seconds=int(elapsed_time)))
                                status["total_time_estimate"]["estimated_remaining_seconds"] = 0
                                status["total_time_estimate"]["estimated_remaining_formatted"] = "0:00:00"
                                status["total_time_estimate"]["estimated_total_seconds"] = round(
                                    elapsed_time, 1)
                                status["total_time_estimate"]["estimated_total_formatted"] = str(
                                    timedelta(seconds=int(elapsed_time)))
                                status["total_time_estimate"]["percent_complete"] = 100.0
                                logger.info(
                                    f"执行成功，总耗时: {status['total_time_estimate']['elapsed_formatted']}")

                            elif event_type == "execution_error":
                                status["error"] = {
                                    "node_id": event_data.get('node_id'),
                                    "message": event_data.get('exception_message'),
                                    "type": event_data.get('exception_type')
                                }
                                # 获取节点描述
                                node_id = event_data.get('node_id')
                                node_desc = self.node_descriptions.get(
                                    node_id, "")
                                logger.error(
                                    f"执行错误: 节点 {node_id} ({node_desc}), 错误信息: {status['error']['message']}")

                            # 创建格式化的事件数据
                            formatted_event = {
                                "event_type": event_type,
                                "event_count": event_count,
                                "timestamp": int(time.time() * 1000),
                                "data": event_data,
                                "status": status.copy()  # 复制当前状态
                            }

                            # 添加节点描述（如果有节点ID）
                            if "node" in event_data:
                                node_id = event_data.get("node")
                                if node_id in self.node_descriptions:
                                    formatted_event["node_description"] = self.node_descriptions[node_id]
                            # 处理缓存事件中的节点列表
                            elif event_type == "execution_cached" and "nodes" in event_data:
                                node_descriptions = {}
                                for node_id in event_data["nodes"]:
                                    if node_id in self.node_descriptions:
                                        node_descriptions[node_id] = self.node_descriptions[node_id]
                                formatted_event["node_descriptions"] = node_descriptions
                            # 处理错误事件中的节点ID
                            elif event_type == "execution_error" and "node_id" in event_data:
                                node_id = event_data.get("node_id")
                                if node_id in self.node_descriptions:
                                    formatted_event["node_description"] = self.node_descriptions[node_id]

                            # 返回事件
                            yield formatted_event

                        except json.JSONDecodeError as e:
                            logger.error(f"JSON解析错误: {e}")
                            yield {
                                "event_type": "error",
                                "data": {
                                    "message": f"JSON解析错误: {e}",
                                    "raw_data": data_str
                                }
                            }

        except requests.exceptions.RequestException as e:
            error_msg = f"请求异常: {str(e)}"
            logger.error(error_msg)
            yield {
                "event_type": "error",
                "data": {
                    "message": error_msg
                }
            }

    def generate_video_sync(self,
                            image_path: Optional[str] = None,
                            image_data: Optional[bytes] = None,
                            image_base64: Optional[str] = None,
                            positive_prompt: str = "这个女孩开心的看着手机,并且非常激动",
                            steps: int = 10,
                            num_frames: int = 81) -> Dict[str, Any]:
        """
        同步生成视频（阻塞直到完成）

        Args:
            image_path: 图片路径（三选一）
            image_data: 图片二进制数据（三选一）
            image_base64: 图片base64编码（三选一）
            positive_prompt: 正向提示词
            steps: 生成步数
            num_frames: 帧数

        Returns:
            包含视频路径和生成状态的字典
        """
        final_status = None

        # 获取所有事件并更新状态
        for event in self.generate_video(
            image_path=image_path,
            image_data=image_data,
            image_base64=image_base64,
            positive_prompt=positive_prompt,
            steps=steps,
            num_frames=num_frames
        ):
            # 更新最终状态
            if "status" in event:
                final_status = event["status"]

            # 如果发生错误，立即返回
            if event["event_type"] == "error":
                return {
                    "success": False,
                    "error": event["data"]["message"],
                    "status": final_status
                }

        # 检查最终状态
        if final_status is None:
            return {
                "success": False,
                "error": "未收到任何事件",
                "status": None
            }

        if final_status["error"]:
            return {
                "success": False,
                "error": final_status["error"],
                "status": final_status
            }

        if not final_status["completed"]:
            return {
                "success": False,
                "error": "生成过程未完成",
                "status": final_status
            }

        # 成功完成
        return {
            "success": True,
            "video_path": final_status["video_path"],
            "total_time": final_status["total_time_estimate"]["elapsed_formatted"],
            "status": final_status
        }


# 测试代码
if __name__ == "__main__":
    # 创建服务实例
    service = I2VService()

    # 检查图片是否存在
    image_path = "image.png"
    if not os.path.exists(image_path):
        logger.error(f"错误: 找不到图片文件 {image_path}")
        exit(1)

    # 设置参数
    params = {
        "image_path": image_path,
        "positive_prompt": "小男孩开着飞船带着小熊，在宇宙中遨游",
        "steps": 7,
        "num_frames": 81
    }

    print(f"开始生成视频，参数: {params}")
    print("-" * 80)

    # 方式1: 流式处理事件
    print("方式1: 流式处理事件")
    for event in service.generate_video(**params):
        print(event)
        event_type = event["event_type"]
        status = event["status"]

        # 根据事件类型打印不同的信息
        if event_type == "executing":
            node_id = event["data"].get("node")
            node_desc = event.get("node_description", "")

            if node_id == "18":
                print(f"🖼️ 正在加载图像... ({node_desc})")
            elif node_id == "17":
                print(f"⚙️ 正在设置迭代参数... ({node_desc})")
            elif node_id == "27":
                print(f"🧠 开始视频生成推理... ({node_desc})")
            elif node_id == "30":
                print(f"🎬 开始拼接视频... ({node_desc})")
            elif node_id is None:
                print("✅ 执行完成")
            else:
                print(f"⚙️ 执行节点: {node_id} ({node_desc})")

        elif event_type == "execution_cached":
            nodes = event["data"].get("nodes", [])
            node_descriptions = event.get("node_descriptions", {})
            cached_nodes = []
            for node_id in nodes:
                node_desc = node_descriptions.get(node_id, "")
                cached_nodes.append(f"{node_id} ({node_desc})")
            print(f"🔄 使用缓存节点: {', '.join(cached_nodes)}")

        elif event_type == "progress":
            node_id = event["data"].get("node")
            value = event["data"].get("value", 0)
            max_val = event["data"].get("max", 100)
            percentage = int((value / max_val) * 100)

            # 获取节点描述
            node_desc = event.get("node_description", "")

            # 获取时间预估
            time_estimate = status["total_time_estimate"]
            remaining_time = time_estimate["estimated_remaining_formatted"]

            if node_id == "27":
                progress_bar = "█" * (percentage // 5) + \
                    "░" * (20 - (percentage // 5))
                print(
                    f"\r🧠 视频生成进度: {progress_bar} {percentage}% - 预计剩余: {remaining_time} ({node_desc})", end="")
            elif node_id == "30":
                progress_bar = "█" * (percentage // 5) + \
                    "░" * (20 - (percentage // 5))
                print(
                    f"\r🎬 视频拼接进度: {progress_bar} {percentage}% - 预计剩余: {remaining_time} ({node_desc})", end="")

        elif event_type == "executed":
            node_id = event["data"].get("node")
            node_desc = event.get("node_description", "")
            if node_id == "30" and status["video_path"]:
                print(f"\n📹 视频已生成: {status['video_path']} ({node_desc})")
                print(
                    f"⏱️ 总耗时: {status['total_time_estimate']['elapsed_formatted']}")

        elif event_type == "execution_success":
            print("\n🎉 执行成功!")
            print(
                f"⏱️ 总耗时: {status['total_time_estimate']['elapsed_formatted']}")

        elif event_type == "execution_error":
            node_id = event["data"].get("node_id")
            node_desc = event.get("node_description", "")
            if not node_desc and node_id in service.node_descriptions:
                node_desc = service.node_descriptions[node_id]
            print(
                f"\n❌ 执行错误: 节点 {node_id} ({node_desc}), 错误信息: {status['error']['message']}")

        elif event_type == "error":
            print(f"\n❌ 服务错误: {event['data']['message']}")

    print("\n" + "-" * 80)

    # # 方式2: 同步等待结果
    # print("\n方式2: 同步等待结果")
    # result = service.generate_video_sync(**params)

    # if result["success"]:
    #     print(f"✅ 视频生成成功: {result['video_path']}")
    #     print(f"⏱️ 总耗时: {result['total_time']}")
    # else:
    #     print(f"❌ 视频生成失败: {result['error']}")

    # print("最终状态:")
    # print(json.dumps(result["status"], indent=2, ensure_ascii=False))
