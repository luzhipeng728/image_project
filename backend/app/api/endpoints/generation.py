import uuid
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from typing import Optional, List
from ...core.auth import verify_token
from ...schemas.schemas import (
    TextToImageRequest,
    ImageToImageRequest,
    GenerationResponse,
    GenerationHistoryResponse,
    ModelResponse
)
from ...services.image_service import ImageService
from ...database.database import get_db
from ...core.config import settings
from fastapi.responses import FileResponse
from pathlib import Path
from urllib.parse import unquote
import logging
import aiohttp
import hashlib
import os
import aiofiles
from PIL import Image

# 创建一个新的路由组，不带前缀
image_router = APIRouter(prefix="")

@image_router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    username: str = Depends(verify_token)
):
    try:
        # 验证文件类型
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="只能上传图片文件")

        # 读取文件内容
        content = await file.read()
        
        # 生成文件名
        file_extension = file.filename.split('.')[-1]
        file_hash = hashlib.md5(content).hexdigest()
        file_path = os.path.join(settings.UPLOAD_DIR, f"{file_hash}.{file_extension}")
        
        # 确保上传目录存在
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        
        # 保存文件
        async with aiofiles.open(file_path, 'wb') as out_file:
            await out_file.write(content)
            
        # 获取图片尺寸
        with Image.open(file_path) as img:
            width, height = img.size
            
        # 保存到数据库
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute('''
                INSERT INTO images (file_path, width, height, file_type)
                VALUES (?, ?, ?, ?)
            ''', (file_path, width, height, file.content_type))
            db.commit()
            
        # 返回文件URL
        return {
            "url": f"{settings.BACKEND_URL}/{file_path}",
            "width": width,
            "height": height
        }
        
    except Exception as e:
        logging.error("文件上传失败", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@image_router.get("/image/{prompt}")
async def get_image_by_prompt(
    prompt: str,
    seed: Optional[int] = None,
    width: int = settings.DEFAULT_WIDTH,
    height: int = settings.DEFAULT_HEIGHT,
    enhance: bool = settings.DEFAULT_ENHANCE,
    model_id: int = 1,
    image_url: Optional[str] = None,
    gen_seed: Optional[int] = None
):
    try:
        print("=== 开始处理图片生成请求 ===")
        print(f"原始 prompt: {prompt}")
        
        # URL解码 prompt
        decoded_prompt = unquote(prompt)
        print(f"解码后 prompt: {decoded_prompt}")
        
        # 如果提供了 image_url，则进行图生图处理
        if image_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as response:
                        if not response.ok:
                            raise HTTPException(status_code=400, detail="无法下载图片，请检查 URL 是否有效")
                        
                        content_type = response.headers.get('content-type', '')
                        if not content_type.startswith('image/'):
                            raise HTTPException(status_code=400, detail="URL 不是有效的图片地址")
                        
                        image_data = await response.read()
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"下载图片失败: {str(e)}")

            # 保存下载的图片
            file_extension = content_type.split('/')[-1]
            file_hash = hashlib.md5(image_data).hexdigest()
            file_path = os.path.join(settings.UPLOAD_DIR, f"{file_hash}.{file_extension}")
            
            # 确保上传目录存在
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            
            # 保存图片文件
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(image_data)

            # 检查缓存
            cache_key = hashlib.md5(f"{image_url}_{decoded_prompt}_{gen_seed}".encode()).hexdigest()
            cached_prompt = await ImageService.get_cached_image_description(image_url, decoded_prompt, gen_seed)
            
            if cached_prompt:
                decoded_prompt = cached_prompt
            else:
                # 调用 LLM 生成图片描述
                decoded_prompt = await ImageService.get_image_description(
                    file_path,
                    decoded_prompt,
                    image_url,
                    gen_seed
                )
                # 保存到缓存
                await ImageService.save_image_description_cache(image_url, decoded_prompt, gen_seed, decoded_prompt)
        
        if seed is None:
            seed = settings.DEFAULT_SEED
        if width is None:
            width = settings.DEFAULT_WIDTH
        if height is None:
            height = settings.DEFAULT_HEIGHT
        if enhance is None:
            enhance = settings.DEFAULT_ENHANCE
            
        # 生成缓存键
        cache_key = ImageService.get_cache_key(decoded_prompt, model_id, seed, width, height, enhance)
        print(f"缓存键: {cache_key}")
        print(f"参数信息: model_id={model_id}, seed={seed}, width={width}, height={height}, enhance={enhance}")
        
        # 检查缓存
        cached_path = ImageService.find_cached_generation(cache_key)
        if cached_path and Path(cached_path).exists():
            print(f"找到缓存图片: {cached_path}")
            # 即使是缓存命中，也创建一个新的生成记录
            await ImageService.create_generation_record(
                username="anonymous",
                prompt=decoded_prompt,
                model_id=model_id,
                seed=seed,
                width=width,
                height=height,
                enhance=enhance,
                cache_key=cache_key,
                cached_path=cached_path
            )
            return FileResponse(cached_path)
        
        print("未找到缓存，开始生成新图片...")
        # 如果没有缓存，生成新图片
        file_path = await ImageService.generate_image(
            username="anonymous",
            prompt=decoded_prompt,
            model_id=model_id,
            seed=seed,
            width=width,
            height=height,
            enhance=enhance
        )
        
        # 确保文件路径存在
        if not Path(file_path).exists():
            raise FileNotFoundError(f"生成的图片文件未找到: {file_path}")
            
        print(f"新图片生成完成: {file_path}")
        print("=== 图片生成请求处理完成 ===")
        return FileResponse(file_path)
    except Exception as e:
        logging.error(f"图片生成错误", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# 将原来的路由处理函数移动到新的路由组
router = APIRouter()

@router.get("/models", response_model=List[ModelResponse])
async def get_models():
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute('SELECT id, name, alias, mapping_name, current_price FROM models')
        models = cursor.fetchall()
        return [dict(model) for model in models]

@router.post("/text-to-image", response_model=GenerationResponse)
async def generate_from_text(
    request: TextToImageRequest,
    username: str = Depends(verify_token)
):
    try:
        # 默认值设置
        if request.seed is None:
            request.seed = settings.DEFAULT_SEED
        if request.width is None:
            request.width = settings.DEFAULT_WIDTH
        if request.height is None:
            request.height = settings.DEFAULT_HEIGHT
        if request.enhance is None:
            request.enhance = settings.DEFAULT_ENHANCE
        
        # 生成缓存键
        cache_key = ImageService.get_cache_key(
            request.prompt, 
            request.model_id, 
            request.seed, 
            request.width, 
            request.height, 
            request.enhance
        )
        
        # 检查缓存
        cached_path = ImageService.find_cached_generation(cache_key)
        if cached_path and Path(cached_path).exists():
            # 如果有缓存，为当前用户创建记录
            await ImageService.create_generation_record(
                username=username,
                prompt=request.prompt,
                model_id=request.model_id,
                seed=request.seed,
                width=request.width,
                height=request.height,
                enhance=request.enhance,
                cache_key=cache_key,
                cached_path=cached_path
            )
            file_path = cached_path
        else:
            # 没有缓存，生成新图片
            file_path = await ImageService.generate_image(
                username=username,
                prompt=request.prompt,
                model_id=request.model_id,
                seed=request.seed,
                width=request.width,
                height=request.height,
                enhance=request.enhance
            )
        
        # 添加后端地址
        image_url = settings.BACKEND_URL + '/' + file_path
        return {"id": uuid.uuid4(), "status": "completed", "image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/image-to-image", response_model=GenerationResponse)
async def generate_from_image(
    request: ImageToImageRequest,
    username: str = Depends(verify_token)
):
    try:
        # 从请求模型中获取参数
        image_url = request.image_url
        prompt = request.prompt or "参考以上图片，保留图片中的整体风格，生成一张优化后的图片，生成的图片描述必须是英文，图片中的存在文字，不需要描述，只需要描述图片中画面信息"
        model_id = request.model_id or 1
        seed = request.seed or 42
        width = request.width or None
        height = request.height or None
        enhance = request.enhance if request.enhance is not None else settings.DEFAULT_ENHANCE
        gen_seed = request.gen_seed or 42

        logging.info(f"开始处理图生图请求 - 图片 URL: {image_url} 提示词: {prompt} 模型ID: {model_id} 种子: {seed} 宽度: {width} 高度: {height} 增强: {enhance} 生成种子: {gen_seed}")

        # 下载并处理图片
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                if not response.ok:
                    raise HTTPException(status_code=400, detail="无法下载图片，请检查 URL 是否有效")
                    
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    raise HTTPException(status_code=400, detail="URL 不是有效的图片地址")
                    
                image_data = await response.read()

        # 保存图片并获取原始尺寸
        file_extension = content_type.split('/')[-1]
        file_hash = hashlib.md5(image_data).hexdigest()
        file_path = os.path.join(settings.UPLOAD_DIR, f"{file_hash}.{file_extension}")

        # 存到数据库
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute('''
                INSERT INTO images (file_path, width, height, file_type)
                VALUES (?, ?, ?, ?)
            ''', (file_path, width, height, file_extension))
            source_image_id = cursor.lastrowid
            db.commit()

        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(image_data)

        # 获取原图尺寸
        with Image.open(file_path) as img:
            original_width, original_height = img.size
            
        # 如果用户没有指定宽高，使用原图尺寸
        if width is None:
            width = original_width
        if height is None:
            height = original_height

        # 生成缓存键（加入宽高信息）
        cache_key = hashlib.md5(f"{image_url}_{prompt}_{gen_seed}_{width}_{height}".encode()).hexdigest()
        
        # 检查图生图描述缓存
        cached_data = await ImageService.get_cached_image_description(image_url, prompt, gen_seed)
        if cached_data:
            print(f"找到缓存的图片描述: {cached_data['prompt']}")
            # 使用缓存的描述生成新图片
            result_path = await ImageService.generate_image(
                username=username,
                prompt=cached_data['prompt'],
                model_id=model_id,
                seed=seed,
                width=width,
                height=height,
                enhance=enhance,
                source_image_id=source_image_id,
                generation_type='image_to_image'
            )
        else:
            # 调用 LLM 生成图片描述
            enhanced_prompt = await ImageService.get_image_description(
                file_path,
                prompt,
                image_url,
                gen_seed
            )
            
            # 保存到缓存（包含宽高信息）
            await ImageService.save_image_description_cache(
                image_url=image_url,
                original_prompt=prompt,
                gen_seed=gen_seed,
                enhanced_prompt=enhanced_prompt,
                width=width,
                height=height
            )
            
            # 使用增强后的提示词生成新图片
            result_path = await ImageService.generate_image(
                username=username,
                prompt=enhanced_prompt,
                model_id=model_id,
                seed=seed,
                width=width,
                height=height,
                enhance=enhance,
                source_image_id=source_image_id,
                generation_type='image_to_image'
            )

        # 返回生成的图片URL
        image_url = settings.BACKEND_URL + '/' + result_path
        return {"id": uuid.uuid4(), "status": "completed", "image_url": image_url}
            
    except Exception as e:
        logging.error("图生图处理失败", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    generation_type: Optional[str] = Query(None, regex="^(text_to_image|image_to_image)$"),
    username: str = Depends(verify_token)
):
    """获取用户的图片生成历史记录"""
    try:
        history = await ImageService.get_generation_history(
            username=username,
            page=page,
            page_size=page_size,
            generation_type=generation_type
        )
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))