import uuid
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, Request, Form
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
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from urllib.parse import unquote
import logging
import aiohttp
import hashlib
import os
import aiofiles
from PIL import Image
from datetime import datetime

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
        file_path = os.path.join(
            settings.UPLOAD_DIR, f"{file_hash}.{file_extension}")

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
                            raise HTTPException(
                                status_code=400, detail="无法下载图片，请检查 URL 是否有效")

                        content_type = response.headers.get('content-type', '')
                        if not content_type.startswith('image/'):
                            raise HTTPException(
                                status_code=400, detail="URL 不是有效的图片地址")

                        image_data = await response.read()
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"下载图片失败: {str(e)}")

            # 保存下载的图片
            file_extension = content_type.split('/')[-1]
            file_hash = hashlib.md5(image_data).hexdigest()
            file_path = os.path.join(
                settings.UPLOAD_DIR, f"{file_hash}.{file_extension}")
            print(f"file_path: {file_path}")
            # 确保上传目录存在
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

            # 保存图片文件
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(image_data)

            # 检查缓存
            cache_key = hashlib.md5(
                f"{image_url}_{decoded_prompt}_{gen_seed}".encode()).hexdigest()
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
        cache_key = ImageService.get_cache_key(
            decoded_prompt, model_id, seed, width, height, enhance)
        print(f"缓存键: {cache_key}")
        print(
            f"参数信息: model_id={model_id}, seed={seed}, width={width}, height={height}, enhance={enhance}")

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
        cursor.execute(
            'SELECT id, name, alias, mapping_name, current_price FROM models')
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


@router.post("/image-to-image")
async def generate_from_image_json(
    request: ImageToImageRequest,
    username: str = Depends(verify_token)
):
    """从已有图片生成新图片 (JSON请求版本)"""
    try:
        # 获取图片路径，处理完整URL的情况
        image_url = request.image_url
        if not image_url:
            raise HTTPException(status_code=400, detail={"message": "缺少图片路径"})

        # 如果是完整URL，转换为本地路径
        if image_url.startswith(settings.BACKEND_URL):
            image_path = image_url.replace(f"{settings.BACKEND_URL}/", "")
        else:
            image_path = image_url

        # 确保图片路径存在
        if not os.path.exists(image_path):
            raise HTTPException(status_code=400, detail={"message": "图片文件不存在"})

        # 获取图片宽高，如果图片宽或高大于 1024 等比缩放最大为 1024
        with Image.open(image_path) as img:
            width, height = img.size
            if width > 1024 or height > 1024:
                ratio = 1024 / max(width, height)
                width = int(width * ratio)
                height = int(height * ratio)

        # 获取源图片ID
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute(
                'SELECT id FROM images WHERE file_path = ?', (image_path,))
            source_image = cursor.fetchone()

            if not source_image:
                raise HTTPException(status_code=404, detail={
                                    "message": "源图片记录不存在"})

            source_image_id = source_image['id']

        # 获取请求参数
        prompt = request.prompt
        model_id = request.model_id
        seed = request.seed
        width = width or settings.DEFAULT_WIDTH
        height = height or settings.DEFAULT_HEIGHT
        project_id = request.project_id

        # 检查缓存
        cache_key = hashlib.md5(
            f"{image_path}_{prompt}_{seed}".encode()).hexdigest()
        cached_prompt = await ImageService.get_cached_image_description(image_path, prompt, seed)

        if cached_prompt:
            enhanced_prompt = cached_prompt
        else:
            # 调用LLM生成图片描述
            try:
                enhanced_prompt = await ImageService._call_llm_for_description(
                    image_path,
                    prompt,
                    seed
                )
                print(f"enhanced_prompt: {enhanced_prompt}")
                # 保存到缓存
                await ImageService.save_image_description_cache(
                    image_url=image_path,
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
                username=username,
                prompt=enhanced_prompt,
                model_id=model_id,
                seed=seed,
                width=width,
                height=height,
                enhance=False,
                source_image_id=source_image_id,  # 添加源图片ID
                generation_type='image_to_image',
                project_id=project_id
            )

            # 返回生成的图片URL
            image_url = settings.BACKEND_URL + '/' + result_path
            return {"id": uuid.uuid4(), "status": "completed", "image_url": image_url, "prompt": enhanced_prompt}
        except HTTPException as e:
            # 直接返回错误信息
            return JSONResponse(status_code=e.status_code, content=e.detail)
    except HTTPException as e:
        # 直接返回HTTP异常
        return JSONResponse(status_code=e.status_code, content=e.detail)
    except Exception as e:
        logging.error(f"图生图处理失败: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"message": "图片生成失败，请稍后重试", "error": str(e)}
        )


@router.get("/history")
async def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    generation_type: Optional[str] = Query(
        None, regex="^(text_to_image|image_to_image)$"),
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


@router.post("/save-results", summary="保存图片生成结果")
async def save_generation_results(
    request: dict,
    username: str = Depends(verify_token)
):
    """
    保存图片生成结果到数据库

    参数:
    - source_image_path: 源图片路径
    - generated_images: 生成的图片列表
    - project_id: 项目ID

    返回:
    - 保存结果
    """
    try:
        source_image_path = request.get("source_image_path")
        generated_images = request.get("generated_images", [])
        project_id = request.get("project_id")

        if not source_image_path or not generated_images:
            raise HTTPException(status_code=400, detail="缺少必要参数")

        # 获取源图片ID
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute(
                'SELECT id FROM images WHERE file_path = ?', (source_image_path,))
            source_image = cursor.fetchone()

            if not source_image:
                raise HTTPException(status_code=404, detail="源图片不存在")

            source_image_id = source_image['id']

            # 保存生成的图片记录
            for gen_image in generated_images:
                # 检查生成的图片是否已存在
                cursor.execute(
                    'SELECT id FROM image_to_image_generations WHERE prompt_image_id = ? AND image_url = ?',
                    (source_image_id,
                     f"{settings.BACKEND_URL}/{gen_image['result_image_path']}")
                )
                existing = cursor.fetchone()

                if not existing:
                    # 获取生成图片的ID
                    cursor.execute(
                        'SELECT id FROM images WHERE file_path = ?', (gen_image['result_image_path'],))
                    result_image = cursor.fetchone()
                    result_image_id = result_image['id'] if result_image else None

                    # 如果生成图片不在images表中，先添加
                    if not result_image_id:
                        cursor.execute(
                            'INSERT INTO images (file_path, project_id, is_generated) VALUES (?, ?, ?)',
                            (gen_image['result_image_path'], project_id, True)
                        )
                        result_image_id = cursor.lastrowid

                    # 保存生成记录
                    cursor.execute('''
                        INSERT INTO image_to_image_generations 
                        (username, model_id, prompt, prompt_image_id, result_image_id, seed, 
                         status, image_url, project_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        username,
                        next((m['id'] for m in cursor.execute(
                            'SELECT id FROM models WHERE alias = ?', (gen_image['model_name'],)).fetchall()), 1),
                        gen_image['prompt'],
                        source_image_id,
                        result_image_id,
                        gen_image.get('seed'),
                        'completed',
                        f"{settings.BACKEND_URL}/{gen_image['result_image_path']}",
                        project_id,
                        gen_image.get(
                            'created_at') or datetime.now().isoformat()
                    ))

            db.commit()

        return {"status": "success", "message": "生成结果已保存"}
    except Exception as e:
        logging.error("保存生成结果失败", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results", summary="获取图片生成结果")
async def get_generation_results(
    source_image: str,
    username: str = Depends(verify_token)
):
    """
    获取基于源图片的生成结果

    参数:
    - source_image: 源图片路径

    返回:
    - 生成结果列表
    """
    try:
        with get_db() as db:
            cursor = db.cursor()

            # 获取源图片ID
            cursor.execute(
                'SELECT id FROM images WHERE file_path = ?', (source_image,))
            source_image_record = cursor.fetchone()

            if not source_image_record:
                return []

            source_image_id = source_image_record['id']

            # 获取生成记录 - 使用image_generations表
            cursor.execute('''
                SELECT g.id, g.prompt, m.alias as model_name, g.seed, 
                       i.file_path as result_image_path, g.created_at
                FROM image_generations g
                JOIN models m ON g.model_id = m.id
                LEFT JOIN images i ON g.result_image_id = i.id
                WHERE g.source_image_id = ? AND g.status = 'completed'
                ORDER BY g.created_at DESC
            ''', (source_image_id,))

            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row['id'],
                    "prompt": row['prompt'],
                    "model_name": row['model_name'],
                    "seed": row['seed'],
                    "result_image_path": row['result_image_path'],
                    "source_image_path": source_image,
                    "created_at": row['created_at']
                })

            # 如果新表中没有数据，尝试从旧表中获取
            if not results:
                cursor.execute('''
                    SELECT g.id, g.prompt, m.alias as model_name, g.seed, 
                           g.image_url, g.created_at, i.file_path as result_image_path
                    FROM image_to_image_generations g
                    JOIN models m ON g.model_id = m.id
                    LEFT JOIN images i ON g.result_image_id = i.id
                    WHERE g.prompt_image_id = ? AND g.status = 'completed'
                    ORDER BY g.created_at DESC
                ''', (source_image_id,))

                for row in cursor.fetchall():
                    result_image_path = row['result_image_path']
                    # 如果有image_url但没有result_image_path，从image_url提取
                    if not result_image_path and row['image_url']:
                        result_image_path = row['image_url'].replace(
                            f"{settings.BACKEND_URL}/", "")

                    results.append({
                        "id": row['id'],
                        "prompt": row['prompt'],
                        "model_name": row['model_name'],
                        "seed": row['seed'],
                        "result_image_path": result_image_path,
                        "source_image_path": source_image,
                        "created_at": row['created_at']
                    })

            return results
    except Exception as e:
        logging.error("获取生成结果失败", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
