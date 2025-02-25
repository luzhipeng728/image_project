import os
import requests
import hashlib
from typing import Optional, Tuple
from fastapi import HTTPException, UploadFile
import aiofiles
from PIL import Image
import logging
import base64
import json
import aiohttp
from pathlib import Path

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
            raise HTTPException(status_code=400, detail="File type not allowed")
        
        # 确保上传目录存在
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        
        # 生成文件名
        file_extension = file.filename.split('.')[-1]
        file_content = await file.read()
        file_hash = hashlib.md5(file_content).hexdigest()
        file_path = os.path.join(settings.UPLOAD_DIR, f"{file_hash}.{file_extension}")
        
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
    async def generate_image(
        username: str,
        prompt: str,
        model_id: int,
        seed: Optional[int] = None,
        width: int = settings.DEFAULT_WIDTH,
        height: int = settings.DEFAULT_HEIGHT,
        enhance: bool = settings.DEFAULT_ENHANCE,
        source_image_id: Optional[int] = None,  # 新增参数，用于图生图
        generation_type: str = 'text_to_image'  # 新增参数，用于区分生成类型
    ) -> str:
        """生成图片并返回文件路径"""
        logging.info(f"开始生成图片 - 用户: {username}, 提示词: {prompt}, 模型ID: {model_id}")
        
        cache_key = ImageService.get_cache_key(prompt, model_id, seed, width, height, enhance)
        logging.info(f"生成的缓存键: {cache_key}")
        
        cached_path = ImageService.find_cached_generation(cache_key)
        if cached_path:
            logging.info(f"找到缓存的图片: {cached_path}")
            return cached_path
        
        with get_db() as db:
            cursor = db.cursor()

            cursor.execute('SELECT name FROM models WHERE id = ?', (model_id,))
            model = cursor.fetchone()
            if not model:
                logging.error(f"未找到模型ID: {model_id}")
                raise HTTPException(status_code=404, detail="Model not found")
            
            logging.info(f"开始调用API生成图片 - 模型: {model['name']}")
            
            # 首先创建生成记录
            cursor.execute('''
                INSERT INTO image_generations 
                (username, prompt, model_id, seed, width, height, enhance, cache_key, status, generation_type, source_image_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            ''', (username, prompt, model_id, seed, width, height, enhance, cache_key, generation_type, source_image_id))
            generation_id = cursor.lastrowid
            db.commit()
            
            try:
                response = requests.post(
                    settings.DEEPINFRA_API_URL,
                    headers={"Authorization": f"Bearer {settings.DEEPINFRA_API_KEY}"},
                    json={
                        "prompt": prompt,
                        "size": f"{width}x{height}",
                        "model": model['name'],
                        "n": 1,
                        "seed": seed if seed is not None else settings.DEFAULT_SEED
                    }
                )
                
                if response.status_code != 200:
                    logging.error(f"API调用失败 - 状态码: {response.status_code}, 响应: {response.text}")
                    raise HTTPException(status_code=500, detail="Image generation failed")
                
                logging.info("API调用成功，开始保存图片")
                # 保存生成的图片
                image_data = response.json()["data"][0]["b64_json"]
                image_data = base64.b64decode(image_data)
                file_path = os.path.join(settings.UPLOAD_DIR, f"{cache_key}.png")
                
                # 确保上传目录存在
                os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
                
                # 保存图片文件
                with open(file_path, "wb") as f:
                    f.write(image_data)
                
                # 先在 images 表中创建记录
                cursor.execute('''
                    INSERT INTO images (file_path, width, height, file_type)
                    VALUES (?, ?, ?, ?)
                ''', (file_path, width, height, 'image/png'))
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
                
            except Exception as e:
                logging.error(f"生成图片时发生错误: {str(e)}", exc_info=True)
                cursor.execute('''
                    UPDATE image_generations
                    SET status = 'failed'
                    WHERE id = ? AND cache_key = ?
                ''', (generation_id, cache_key))
                db.commit()
                raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def create_generation_record(
        username: str,
        prompt: str,
        model_id: int,
        seed: Optional[int],
        width: int,
        height: int,
        enhance: bool,
        cache_key: str,
        cached_path: str,
        source_image_id: Optional[int] = None,  # 新增参数
        generation_type: str = 'text_to_image'  # 新增参数
    ) -> None:
        """为缓存命中的情况创建生成记录"""
        with get_db() as db:
            cursor = db.cursor()
            
            # 获取已存在图片的ID
            cursor.execute('SELECT id FROM images WHERE file_path = ?', (cached_path,))
            image_record = cursor.fetchone()
            image_id = image_record['id'] if image_record else None
            
            if image_id:
                # 检查用户是否已经有这个生成记录
                cursor.execute('''
                    SELECT id FROM image_generations 
                    WHERE username = ? AND cache_key = ?
                ''', (username, cache_key))
                existing_record = cursor.fetchone()
                
                # 如果用户没有这个生成记录，则创建一个新的
                if not existing_record:
                    cursor.execute('''
                        INSERT INTO image_generations 
                        (username, prompt, model_id, seed, width, height, enhance, cache_key, 
                         status, result_image_id, generation_type, source_image_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?)
                    ''', (username, prompt, model_id, seed, width, height, enhance, 
                          cache_key, image_id, generation_type, source_image_id))
                    db.commit()

    @staticmethod
    async def get_cached_image_description(image_url: str, prompt: str, gen_seed: Optional[int]) -> Optional[dict]:
        """获取缓存的图片描述，返回包含提示词和尺寸信息的字典"""
        cache_key = hashlib.md5(f"{image_url}_{prompt}_{gen_seed}".encode()).hexdigest()
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
        image_url: str,
        original_prompt: str,
        gen_seed: Optional[int],
        enhanced_prompt: str,
        width: int,
        height: int
    ):
        """保存图片描述到缓存，包含尺寸信息"""
        cache_key = hashlib.md5(f"{image_url}_{original_prompt}_{gen_seed}".encode()).hexdigest()
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO image_description_cache 
                (cache_key, original_prompt, enhanced_prompt, width, height, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            ''', (cache_key, original_prompt, enhanced_prompt, width, height))
            db.commit()

    @staticmethod
    async def get_image_description(
        file_path: str,
        prompt: Optional[str],
        image_url: str,
        gen_seed: Optional[int]
    ) -> str:
        try:
            # 获取图片尺寸
            with Image.open(file_path) as img:
                width, height = img.size

            # 调用 LLM 获取图片描述
            enhanced_prompt = await ImageService._call_llm_for_description(file_path, prompt, gen_seed)
            
            # 保存到缓存，使用实际的图片尺寸
            await ImageService.save_image_description_cache(
                image_url=image_url,
                original_prompt=prompt,
                gen_seed=gen_seed,
                enhanced_prompt=enhanced_prompt,
                width=width,
                height=height
            )
            
            return enhanced_prompt
        except Exception as e:
            logging.error("获取图片描述失败", exc_info=True)
            raise

    @staticmethod
    async def _call_llm_for_description(image_path: str, prompt: str, seed: Optional[int] = None) -> str:
        """调用 LLM API 获取图片描述"""
        try:
            # 读取图片并转换为 base64
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
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
                        json_match = content.split("```json")[-1].split("```")[0].strip()
                        json_content = json.loads(json_match)
                    except:
                        # 如果没有代码块，直接尝试解析整个内容
                        json_content = json.loads(content)
                    
                    enhanced_prompt = json_content.get("prompt")
                    
                    if not enhanced_prompt:
                        raise ValueError("无法从 LLM 响应中提取有效的提示词")
                    
                    return enhanced_prompt

        except Exception as e:
            logging.error(f"获取图片描述失败: {str(e)}", exc_info=True)
            # 如果失败，返回原始提示词
            return prompt 

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