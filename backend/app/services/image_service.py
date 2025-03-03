import os
import random
import requests
import hashlib
from typing import Optional, Tuple, Dict, List
from fastapi import HTTPException, UploadFile
import aiofiles
from PIL import Image
import logging
import base64
import json
import aiohttp
from pathlib import Path
import asyncio

from ..core.config import settings
from ..database.database import get_db
from ..models.models import TextToImageGeneration, ImageToImageGeneration


class ImageService:
    @staticmethod
    async def save_upload_file(file: UploadFile) -> Tuple[str, int, int]:
        """保存上传的文件并返回文件路径和尺寸"""
        logging.info(f"开始处理上传文件: {file.filename}")

        if file.content_type not in settings.ALLOWED_FILE_TYPES:
            logging.warning(f"不支持的文件类型: {file.content_type}")
            raise HTTPException(
                status_code=400, detail="File type not allowed")

        # 确保上传目录存在
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

        # 生成文件名
        file_extension = file.filename.split('.')[-1]
        file_content = await file.read()
        file_hash = hashlib.md5(file_content).hexdigest()
        file_path = os.path.join(
            settings.UPLOAD_DIR, f"{file_hash}.{file_extension}")

        # 保存文件
        async with aiofiles.open(file_path, 'wb') as out_file:
            await out_file.write(file_content)

        # 获取图片尺寸
        with Image.open(file_path) as img:
            width, height = img.size

        logging.info(f"文件已保存到: {file_path}, 尺寸: {width}x{height}")
        return file_path, width, height

    @staticmethod
    def get_cache_key(prompt: str, model_id: int, seed: Optional[int], width: int, height: int, enhance: bool) -> str:
        """生成缓存键"""
        components = [
            prompt,
            str(model_id),
            str(seed if seed is not None else settings.DEFAULT_SEED),
            str(width),
            str(height),
            "1" if enhance else "0"
        ]
        return hashlib.md5("_".join(components).encode()).hexdigest()

    @staticmethod
    def find_cached_generation(cache_key: str) -> Optional[str]:
        # 这边直接找图片地址的cache是否存在这个图片uploads目录下
        file_path = os.path.join(settings.UPLOAD_DIR, f"{cache_key}.png")
        if os.path.exists(file_path):
            return file_path
        return None

    @staticmethod
    async def get_model_by_id(model_id: int) -> Optional[dict]:
        """根据ID获取模型信息"""
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute(
                'SELECT id, name, alias, mapping_name FROM models WHERE id = ?', (model_id,))
            model = cursor.fetchone()
            if model:
                return {
                    'id': model['id'],
                    'name': model['name'],
                    'alias': model['alias'],
                    'mapping_name': model['mapping_name']
                }
            return None

    @staticmethod
    async def generate_image(
        username: str,
        prompt: str,
        model_id: int,
        seed: Optional[int] = None,
        width: int = 512,
        height: int = 512,
        enhance: bool = False,
        source_image_id: Optional[int] = None,
        generation_type: str = 'text_to_image',
        project_id: Optional[int] = None
    ) -> str:
        """生成图片并返回文件路径"""
        # 确保prompt是字符串类型
        prompt_str = str(prompt) if prompt is not None else ""
        logging.info(f"开始生成图片 - 提示词: {prompt_str[:50]}...")

        # 检查图片尺寸是否超过限制
        if width > 2048 or height > 2048:
            logging.warning(f"图片尺寸超过限制: {width}x{height}, 最大允许尺寸为2048x2048")
            raise HTTPException(
                status_code=422,
                detail={"message": "图片尺寸超过限制，请使用较小的尺寸",
                        "max_size": 2048, "current_size": f"{width}x{height}"}
            )

        # 生成缓存键
        cache_key = ImageService.get_cache_key(
            prompt, model_id, seed, width, height, enhance)

        # 检查缓存
        cached_path = ImageService.find_cached_generation(cache_key)
        if cached_path:
            logging.info(f"找到缓存的图片: {cached_path}")
            return cached_path

        # 创建生成记录
        generation_id = await ImageService.create_generation_record(
            username, prompt, model_id, seed, width, height, enhance, source_image_id, generation_type
        )

        # 获取模型信息
        model = await ImageService.get_model_by_id(model_id)
        if not model:
            raise HTTPException(status_code=404, detail={
                                "message": "找不到指定的模型"})

        # 连接数据库
        db = get_db()
        cursor = db.cursor()

        try:
            # 调用API生成图片
            logging.info(f"开始调用API生成图片 - 模型: {model['name']}")

            try:
                response = requests.post(
                    f"https://api.deepinfra.com/v1/openai/images/generations",
                    headers={
                        "Authorization": f"Bearer {settings.DEEPINFRA_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "prompt": prompt,
                        "size": f"{width}x{height}",
                        "model": model['name'],
                        "n": 1,
                        "seed": seed if seed is not None else settings.DEFAULT_SEED
                    }
                )

                if response.status_code != 200:
                    error_message = f"API调用失败 - 状态码: {response.status_code}"
                    error_detail = {"message": "图片生成失败"}

                    try:
                        error_response = response.json()
                        logging.error(f"{error_message}, 响应: {response.text}")

                        # 处理特定错误类型
                        if response.status_code == 422 and "detail" in error_response:
                            for detail in error_response["detail"]:
                                if "size" in detail.get("loc", []) and "Width and height" in detail.get("msg", ""):
                                    error_detail = {
                                        "message": "图片尺寸超过API限制，请使用较小的尺寸",
                                        "max_size": 2048,
                                        "current_size": f"{width}x{height}"
                                    }
                    except:
                        pass

                    # 更新生成记录为失败状态
                    cursor.execute('''
                        UPDATE image_generations
                        SET status = 'failed'
                        WHERE id = ? AND cache_key = ?
                    ''', (generation_id, cache_key))
                    db.commit()

                    raise HTTPException(status_code=422, detail=error_detail)

                logging.info("API调用成功，开始保存图片")
                # 保存生成的图片
                image_data = response.json()["data"][0]["b64_json"]
                image_data = base64.b64decode(image_data)
                file_path = os.path.join(
                    settings.UPLOAD_DIR, f"{cache_key}.png")

                # 确保上传目录存在
                os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

                # 保存图片文件
                with open(file_path, "wb") as f:
                    f.write(image_data)

                # 先在 images 表中创建记录
                cursor.execute('''
                    INSERT INTO images (file_path, width, height, file_type, project_id, is_generated)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (file_path, width, height, 'image/png', project_id, True))
                image_id = cursor.lastrowid

                # 更新生成记录
                cursor.execute('''
                    UPDATE image_generations
                    SET status = 'completed', result_image_id = ?
                    WHERE id = ? AND cache_key = ?
                ''', (image_id, generation_id, cache_key))
                db.commit()

                logging.info(f"图片已保存到: {file_path}")
                return file_path

            except HTTPException as http_ex:
                # 直接重新抛出HTTP异常
                raise http_ex
            except Exception as e:
                logging.error(f"生成图片时发生错误: {str(e)}", exc_info=True)
                error_detail = {"message": "图片生成过程中发生错误"}

                # 检查是否为图片识别错误
                if "cannot identify image file" in str(e):
                    error_detail = {"message": "无法识别的图片文件格式"}

                # 更新生成记录为失败状态
                cursor.execute('''
                    UPDATE image_generations
                    SET status = 'failed'
                    WHERE id = ? AND cache_key = ?
                ''', (generation_id, cache_key))
                db.commit()

                raise HTTPException(status_code=400, detail=error_detail)

        except HTTPException as http_ex:
            # 直接重新抛出HTTP异常
            raise http_ex
        except Exception as e:
            logging.error(f"生成图片过程中发生未知错误: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail={
                                "message": "服务器内部错误，请稍后重试"})

    @staticmethod
    async def create_generation_record(
        username: str,
        prompt: str,
        model_id: int,
        seed: Optional[int],
        width: int,
        height: int,
        enhance: bool,
        source_image_id: Optional[int] = None,  # 新增参数
        generation_type: str = 'text_to_image',  # 新增参数
        cache_key: Optional[str] = None,
        cached_path: Optional[str] = None
    ) -> int:
        """创建生成记录并返回记录ID"""
        with get_db() as db:
            cursor = db.cursor()

            # 如果提供了缓存路径，获取已存在图片的ID
            image_id = None
            if cached_path:
                cursor.execute(
                    'SELECT id FROM images WHERE file_path = ?', (cached_path,))
                image_record = cursor.fetchone()
                image_id = image_record['id'] if image_record else None

            # 生成缓存键（如果未提供）
            if not cache_key:
                cache_key = ImageService.get_cache_key(
                    prompt, model_id, seed, width, height, enhance)

            # 检查用户是否已经有这个生成记录
            if image_id:
                cursor.execute('''
                    SELECT id FROM image_generations 
                    WHERE username = ? AND cache_key = ?
                ''', (username, cache_key))
                existing_record = cursor.fetchone()

                # 如果用户已有这个生成记录，直接返回记录ID
                if existing_record:
                    return existing_record['id']

            # 创建新的生成记录
            cursor.execute('''
                INSERT INTO image_generations 
                (username, prompt, model_id, seed, width, height, enhance, cache_key, 
                 status, result_image_id, generation_type, source_image_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (username, prompt, model_id, seed, width, height, enhance,
                  cache_key, 'completed' if image_id else 'pending', image_id, generation_type, source_image_id))

            generation_id = cursor.lastrowid
            db.commit()
            return generation_id

    @staticmethod
    async def get_cached_image_description(image_path: str, prompt: str, gen_seed: Optional[int]) -> Optional[dict]:
        """获取缓存的图片描述"""
        cache_key = hashlib.md5(
            f"{image_path}_{prompt}_{gen_seed}".encode()).hexdigest()
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute('''
                SELECT enhanced_prompt, width, height
                FROM image_description_cache
                WHERE cache_key = ?
            ''', (cache_key,))
            result = cursor.fetchone()
            if result:
                return {
                    'prompt': result['enhanced_prompt'],
                    'width': result['width'],
                    'height': result['height']
                }
            return None

    @staticmethod
    async def save_image_description_cache(
        image_url: str,  # 这里保持参数名不变，但实际上是文件路径
        original_prompt: str,
        gen_seed: Optional[int],
        enhanced_prompt: str,
        width: int,
        height: int
    ):
        """保存图片描述到缓存"""
        cache_key = hashlib.md5(
            f"{image_url}_{original_prompt}_{gen_seed}".encode()).hexdigest()
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO image_description_cache 
                (cache_key, original_prompt, enhanced_prompt, width, height, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            ''', (cache_key, original_prompt, enhanced_prompt, width, height))
            db.commit()

    # @staticmethod
    # async def get_image_description(
    #     file_path: str,
    #     prompt: Optional[str],
    #     image_url: str,  # 这个参数可以保留，但实际上也是文件路径
    #     gen_seed: Optional[int]
    # ) -> str:
    #     try:
    #         # 获取图片尺寸
    #         with Image.open(file_path) as img:
    #             width, height = img.size

    #         # 调用 LLM 获取图片描述
    #         enhanced_prompt = await ImageService._call_llm_for_description(file_path, prompt, gen_seed)

    #         # 保存到缓存
    #         await ImageService.save_image_description_cache(
    #             image_url=file_path,  # 使用文件路径
    #             original_prompt=prompt,
    #             gen_seed=gen_seed,
    #             enhanced_prompt=enhanced_prompt,
    #             width=width,
    #             height=height
    #         )

    #         return enhanced_prompt
    #     except Exception as e:
    #         logging.error("获取图片描述失败", exc_info=True)
    #         return prompt if prompt else ""

    @staticmethod
    async def _call_llm_for_description(image_path: str, prompt: str, seed: Optional[int] = None) -> str:
        """调用 LLM API 获取图片描述"""
        max_retries = 3
        retry_count = 0
        backoff_time = 2  # 初始等待时间（秒）
        
        while retry_count < max_retries:
            try:
                # 读取图片并转换为 base64
                base64_image = ""
                with open(image_path, "rb") as image_file:
                    base64_image = base64.b64encode(
                        image_file.read()).decode('utf-8')

                # print(base64_image)

                # 构建 API 请求
                payload = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"{prompt} 使用json格式回复，回复的格式必须是{{prompt:\"图片描述\"}}, 图片描述必须是英文"
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    "model": "gpt-4o-mini",
                    "json": True
                }

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.HYPRLAB_API_KEY}"
                }

                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                    async with session.post(
                        "https://api.hyprlab.io/v1/chat/completions",
                        headers=headers,
                        json=payload
                    ) as response:
                        if not response.ok:
                            error_text = await response.text()
                            raise Exception(f"LLM API 调用失败: {error_text}")

                        result = await response.json()

                        # 解析响应内容
                        content = result["choices"][0]["message"]["content"]

                        # 尝试解析 JSON 内容
                        try:
                            # 首先尝试查找 JSON 代码块
                            json_match = content.split(
                                "```json")[-1].split("```")[0].strip()
                            json_content = json.loads(json_match)
                        except:
                            # 如果没有代码块，直接尝试解析整个内容
                            json_content = json.loads(content)

                        enhanced_prompt = json_content.get("prompt")

                        if not enhanced_prompt:
                            raise ValueError("无法从 LLM 响应中提取有效的提示词")

                        return enhanced_prompt

            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logging.error(f"调用LLM失败，已重试{max_retries}次，放弃重试: {str(e)}")
                    raise  # 重试耗尽后，重新抛出异常
                
                # 计算指数退避时间 (2, 4, 8秒...)
                wait_time = backoff_time * (2 ** (retry_count - 1))
                logging.warning(f"调用LLM失败，将在{wait_time}秒后进行第{retry_count+1}次重试: {str(e)}")
                
                # 等待一段时间后重试
                await asyncio.sleep(wait_time)

    @staticmethod
    async def get_generation_history(
        username: str,
        page: int = 1,
        page_size: int = 10,
        generation_type: Optional[str] = None
    ) -> dict:
        """获取用户的图片生成历史记录，支持分页和类型筛选"""
        with get_db() as db:
            cursor = db.cursor()

            # 构建基础查询
            query = '''
                SELECT 
                    g.*,
                    m.name as model_name,
                    m.alias as model_alias,
                    si.file_path as source_image_path,
                    ri.file_path as result_image_path
                FROM image_generations g
                LEFT JOIN models m ON g.model_id = m.id
                LEFT JOIN images si ON g.source_image_id = si.id
                LEFT JOIN images ri ON g.result_image_id = ri.id
                WHERE g.username = ?
            '''
            params = [username]

            # 添加类型筛选
            if generation_type:
                query += ' AND g.generation_type = ?'
                params.append(generation_type)

            # 获取总记录数
            count_query = f"SELECT COUNT(*) FROM ({query}) as count_table"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]

            # 添加排序和分页
            query += ' ORDER BY g.created_at DESC LIMIT ? OFFSET ?'
            params.extend([page_size, (page - 1) * page_size])

            # 执行查询
            cursor.execute(query, params)
            records = cursor.fetchall()

            # 转换结果为字典列表
            results = []
            for record in records:
                result = {
                    'id': record['id'],
                    'generation_type': record['generation_type'],
                    'prompt': record['prompt'],
                    'enhanced_prompt': record['enhanced_prompt'],
                    'source_image_path': settings.BACKEND_URL + '/' + record['source_image_path'] if record['source_image_path'] else None,
                    'result_image_path': settings.BACKEND_URL + '/' + record['result_image_path'] if record['result_image_path'] else None,
                    'model_name': record['model_name'],
                    'model_alias': record['model_alias'],
                    'created_at': record['created_at'],
                    'status': record['status'],
                    'width': record['width'],
                    'height': record['height'],
                    'seed': record['seed'],
                    'enhance': record['enhance']
                }
                results.append(result)

            return {
                'total': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size,
                'records': results
            }

    @staticmethod
    async def generate_image_to_image(
        image_url: str,
        prompt: str,
        model_id: int,
        project_id: Optional[int] = None,
        seed: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        enhance: bool = False,
        username: str = "admin",  # 默认用户名
        source_image_path: Optional[str] = None
    ) -> dict:
        """图像到图像生成，返回生成结果的字典"""
        logging.info(f"开始图像到图像生成 - 源图片: {image_url}, 提示词: {prompt[:50]}...")

        # 确保prompt是字符串类型
        prompt_str = str(prompt) if prompt is not None else ""

        # 从URL中提取文件路径
        if image_url.startswith(settings.BACKEND_URL):
            source_image_path = image_url[len(settings.BACKEND_URL) + 1:]
        else:
            source_image_path = image_url

        print("--------------------------------")
        print(f"source_image_path: {source_image_path}")
        print("--------------------------------")

        # 如果是相对路径，转换为绝对路径
        if not os.path.isabs(source_image_path) and not source_image_path.startswith('http'):
            # 获取backend目录的绝对路径
            backend_dir = os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))
            source_image_path = os.path.join(backend_dir, source_image_path)
            logging.info(f"转换为绝对路径: {source_image_path}")

        # 检查源图片是否存在
        if not os.path.exists(source_image_path) and not source_image_path.startswith('http'):
            logging.error(f"源图片不存在: {source_image_path}")
            raise HTTPException(status_code=404, detail={"message": "源图片不存在"})

        # 如果没有指定宽高，获取源图片的宽高
        if width is None or height is None:
            try:
                with Image.open(source_image_path) as img:
                    orig_width, orig_height = img.size
                    width = width or orig_width
                    height = height or orig_height
            except Exception as e:
                logging.error(f"无法读取源图片尺寸: {str(e)}")
                width = width or 512
                height = height or 512

        # 检查图片尺寸是否超过限制
        if width > 2048 or height > 2048:
            logging.warning(f"图片尺寸超过限制: {width}x{height}, 最大允许尺寸为2048x2048")
            raise HTTPException(
                status_code=422,
                detail={"message": "图片尺寸超过限制，请使用较小的尺寸",
                        "max_size": 2048, "current_size": f"{width}x{height}"}
            )

        # 生成缓存键
        cache_key = ImageService.get_cache_key(
            prompt, model_id, seed, width, height, enhance)

        # 检查缓存
        cached_path = ImageService.find_cached_generation(cache_key)
        if cached_path:
            logging.info(f"找到缓存的图片: {cached_path}")
            return {
                "file_path": cached_path,
                "url": f"{settings.BACKEND_URL}/{cached_path}",
                "width": width,
                "height": height,
                "seed": seed,
                "from_cache": True,
                "source_image_path": source_image_path,
                "prompt": prompt
            }

        # 获取源图片的ID
        source_image_id = None
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute(
                'SELECT id FROM images WHERE file_path = ?', (source_image_path,))
            result = cursor.fetchone()
            if result:
                source_image_id = result['id']

        # 创建生成记录
        generation_id = await ImageService.create_generation_record(
            username, prompt, model_id, seed, width, height, enhance,
            source_image_id, 'image_to_image', cache_key, source_image_path
        )

        # 获取模型信息
        model = await ImageService.get_model_by_id(model_id)
        if not model:
            raise HTTPException(status_code=404, detail={
                                "message": "找不到指定的模型"})

        # 连接数据库
        db = get_db()
        cursor = db.cursor()

        try:
            # 调用API生成图片
            logging.info(f"开始调用API生成图片 - 模型: {model['name']}")

            try:
                # 读取源图片并转换为base64
                with open(source_image_path, "rb") as image_file:
                    source_image_data = base64.b64encode(
                        image_file.read()).decode('utf-8')

                # 使用传入的提示词，不再使用硬编码的模板
                # 提示词已经在队列处理或单张图片生成接口中通过LLM增强过
                enhanced_prompt = prompt_str

                # 调用API进行图像到图像生成（使用text-to-image API）
                response = requests.post(
                    f"https://api.deepinfra.com/v1/openai/images/generations",
                    headers={
                        "Authorization": f"Bearer {settings.DEEPINFRA_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "prompt": enhanced_prompt,
                        "size": f"{width}x{height}",
                        "model": model['name'],
                        "n": 1,
                        "seed": seed if seed is not None else settings.DEFAULT_SEED
                    }
                )

                if response.status_code != 200:
                    error_message = f"API调用失败 - 状态码: {response.status_code}"
                    error_detail = {"message": "图片生成失败"}

                    try:
                        error_response = response.json()
                        logging.error(f"{error_message}, 响应: {response.text}")

                        # 处理特定错误类型
                        if response.status_code == 422 and "detail" in error_response:
                            for detail in error_response["detail"]:
                                if "size" in detail.get("loc", []) and "Width and height" in detail.get("msg", ""):
                                    error_detail = {
                                        "message": "图片尺寸超过API限制，请使用较小的尺寸",
                                        "max_size": 2048,
                                        "current_size": f"{width}x{height}"
                                    }
                    except:
                        pass

                    # 更新生成记录为失败状态
                    cursor.execute('''
                        UPDATE image_generations
                        SET status = 'failed'
                        WHERE id = ? AND cache_key = ?
                    ''', (generation_id, cache_key))
                    db.commit()

                    raise HTTPException(status_code=422, detail=error_detail)

                logging.info("API调用成功，开始保存图片")
                # 保存生成的图片
                image_data = response.json()["data"][0]["b64_json"]
                image_data = base64.b64decode(image_data)
                file_path = os.path.join(
                    settings.UPLOAD_DIR, f"{cache_key}.png")

                # 确保上传目录存在
                os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

                # 保存图片文件
                with open(file_path, "wb") as f:
                    f.write(image_data)

                # 先在 images 表中创建记录
                cursor.execute('''
                    INSERT INTO images (file_path, width, height, file_type, project_id, is_generated)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (file_path, width, height, 'image/png', project_id, True))
                image_id = cursor.lastrowid

                # 更新生成记录
                cursor.execute('''
                    UPDATE image_generations
                    SET status = 'completed', result_image_id = ?
                    WHERE id = ? AND cache_key = ?
                ''', (image_id, generation_id, cache_key))
                db.commit()

                logging.info(f"图片已保存到: {file_path}")

                # 返回结果
                return {
                    "file_path": file_path,
                    "url": f"{settings.BACKEND_URL}/{file_path}",
                    "width": width,
                    "height": height,
                    "seed": seed,
                    "from_cache": False,
                    "source_image_path": source_image_path,
                    "prompt": enhanced_prompt
                }

            except HTTPException as http_ex:
                # 直接重新抛出HTTP异常
                raise http_ex
            except Exception as e:
                logging.error(f"生成图片时发生错误: {str(e)}", exc_info=True)
                error_detail = {"message": "图片生成过程中发生错误"}

                # 检查是否为图片识别错误
                if "cannot identify image file" in str(e):
                    error_detail = {"message": "无法识别的图片文件格式"}

                # 更新生成记录为失败状态
                cursor.execute('''
                    UPDATE image_generations
                    SET status = 'failed'
                    WHERE id = ? AND cache_key = ?
                ''', (generation_id, cache_key))
                db.commit()

                raise HTTPException(status_code=400, detail=error_detail)

        except HTTPException as http_ex:
            # 直接重新抛出HTTP异常
            raise http_ex
        except Exception as e:
            logging.error(f"生成图片过程中发生未知错误: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail={
                                "message": "服务器内部错误，请稍后重试"})

    @staticmethod
    async def generate_image_from_task(task_data: Dict) -> Dict:
        """从任务数据生成图片"""
        try:
            # 从任务数据中提取所需参数，安全地处理所有数值参数
            prompt = task_data.get("prompt", "")
            model_id_raw = task_data.get("model_id")
            model_id = int(model_id_raw) if model_id_raw is not None and model_id_raw != "None" else 0
            
            width_raw = task_data.get("width")
            width = int(width_raw) if width_raw is not None and width_raw != "None" else 1024
            
            height_raw = task_data.get("height")
            height = int(height_raw) if height_raw is not None and height_raw != "None" else 1024
            
            source_image_path = task_data.get("source_image_path")
            
            # 安全地转换 project_id 和 image_id
            project_id = task_data.get("project_id")
            project_id = int(project_id) if project_id is not None and project_id != "None" else None
            
            image_id = task_data.get("image_id")
            image_id = int(image_id) if image_id is not None and image_id != "None" else None
            
            username = task_data.get("username", "admin")
            
            # 解析seeds数组
            seeds = json.loads(task_data.get("seeds", "[]"))
            if not seeds:
                seeds = [None]  # 如果没有指定seeds，至少生成一张
            
            # 获取图片的绝对路径
            if source_image_path.startswith(settings.BACKEND_URL):
                source_image_path = source_image_path[len(settings.BACKEND_URL) + 1:]
            
            # 如果是相对路径，转换为绝对路径
            if not os.path.isabs(source_image_path) and not source_image_path.startswith('http'):
                backend_dir = os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))))
                source_image_path = os.path.join(backend_dir, source_image_path)
                logging.info(f"转换为绝对路径: {source_image_path}")
            
            # 创建并行任务列表
            tasks = []
            for seed in seeds:
                # 检查缓存中是否有增强的 prompt
                cached_prompt = await ImageService.get_cached_image_description(source_image_path, prompt, seed)
                
                if cached_prompt:
                    enhanced_prompt = cached_prompt.get('prompt', prompt)
                else:
                    # 调用LLM生成图片描述
                    try:
                        enhanced_prompt = await ImageService._call_llm_for_description(
                            source_image_path,
                            prompt,
                            seed
                        )
                        logging.info(f"enhanced_prompt: {enhanced_prompt}")
                        # 保存到缓存
                        await ImageService.save_image_description_cache(
                            image_url=source_image_path,
                            original_prompt=prompt,
                            gen_seed=seed,
                            enhanced_prompt=enhanced_prompt,
                            width=width,
                            height=height
                        )
                    except Exception as e:
                        logging.error(f"获取图片描述失败: {str(e)}", exc_info=True)
                        enhanced_prompt = prompt
                
                # 为每个seed创建一个生成任务
                tasks.append(
                    ImageService.generate_image(
                        username=username,
                        prompt=enhanced_prompt,  # 使用增强后的 prompt
                        model_id=model_id,
                        seed=seed,
                        width=width,
                        height=height,
                        enhance=False,
                        source_image_id=image_id,  # 添加源图片ID
                        generation_type='image_to_image',
                        project_id=project_id
                    )
                )
            
            # 并行执行所有任务
            results = await asyncio.gather(*tasks)
            
            # 处理所有结果
            processed_results = []
            for i, result in enumerate(results):
                processed_results.append({
                    "status": "success",
                    "file_path": result,  # generate_image 返回的是文件路径
                    "url": f"{settings.BACKEND_URL}/{result}",
                    "width": str(width),
                    "height": str(height),
                    "seed": str(seeds[i] if i < len(seeds) else ""),
                    "prompt": prompt,
                    "variant_index": i,
                    "source_image_id": image_id,
                    "project_id": project_id
                })
            
            return {
                "status": "success",
                "variants": processed_results,
                "source_image_id": image_id,
                "project_id": project_id
            }
            
        except Exception as e:
            raise Exception(f"图片生成失败: {str(e)}")

    @staticmethod
    async def get_project_images(project_id: int, db) -> List[Dict]:
        """获取项目中的所有图片"""
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, file_path, width, height
            FROM images
            WHERE project_id = ? AND is_generated = FALSE
            """,
            (project_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    async def create_tasks_from_project(project_id: int, model_id: int, db) -> List[Dict]:
        """从项目创建任务列表"""
        # 获取项目中的所有原始图片
        images = await ImageService.get_project_images(project_id, db)
        
        tasks = []
        for image in images:
            # 为每个图片创建3个不同种子的任务
            random_seeds = random.sample(range(1, 1000000), 3)
            seeds = [random_seeds[0], random_seeds[1], random_seeds[2]]
            
            task = {
                "image_id": image["id"],
                "image_url": f"http://36.213.56.75:8002/uploads/{image['file_path']}",
                "prompt": "参考以上图片，保留图片中的整体风格，生成一张优化后的图片，生成的图片描述必须是英文，图片中的存在文字，不需要描述，只需要描述图片中画面信息",
                "width": image["width"],
                "height": image["height"],
                "seeds": seeds,
                "source_image_path": image["file_path"]
            }
            tasks.append(task)
        
        return tasks
