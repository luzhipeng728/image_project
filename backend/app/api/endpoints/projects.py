from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from typing import List, Optional
import os
import shutil
import sqlite3
from datetime import datetime
import zipfile
import tempfile
import uuid
import re
import hashlib
import random
import asyncio
import logging
import aiofiles

from ...database.database import get_db
from ...core.config import settings
from ...core.auth import get_current_user, verify_token
from ...models.models import User
from ...schemas.schemas import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    ImageResponse, ImageUploadRequest, UserResponse,
    BatchGenerationRequest
)

router = APIRouter()

# 创建项目


@router.post("/", response_model=ProjectResponse, summary="创建新项目")
async def create_project(
    project: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    创建新项目

    参数:
    - project: 项目创建信息，包含名称和描述

    返回:
    - 创建成功的项目信息
    """
    cursor = db.cursor()

    # 检查项目名称是否已存在
    cursor.execute(
        "SELECT id FROM projects WHERE name = ? AND owner_id = ?",
        (project.name, current_user.username)
    )
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="您已有同名项目")

    now = datetime.now().isoformat()
    cursor.execute(
        """
        INSERT INTO projects (name, description, owner_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (project.name, project.description, current_user.username, now, now)
    )
    db.commit()

    project_id = cursor.lastrowid

    # 获取创建的项目
    cursor.execute(
        """
        SELECT id, name, description, owner_id, created_at, updated_at
        FROM projects WHERE id = ?
        """,
        (project_id,)
    )
    project_data = cursor.fetchone()

    return {
        "id": project_data["id"],
        "name": project_data["name"],
        "description": project_data["description"],
        "owner_id": project_data["owner_id"],
        "created_at": project_data["created_at"],
        "updated_at": project_data["updated_at"]
    }

# 获取项目列表


@router.get("/", response_model=List[ProjectResponse], summary="获取项目列表")
async def get_projects(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    获取当前用户的项目列表

    参数:
    - skip: 跳过的记录数，用于分页
    - limit: 返回的最大记录数，用于分页

    返回:
    - 项目列表
    """
    cursor = db.cursor()

    # 管理员可以看到所有项目
    if current_user.is_admin:
        cursor.execute(
            """
            SELECT id, name, description, owner_id, created_at, updated_at
            FROM projects
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, skip)
        )
    else:
        # 普通用户只能看到自己的项目
        cursor.execute(
            """
            SELECT id, name, description, owner_id, created_at, updated_at
            FROM projects
            WHERE owner_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (current_user.username, limit, skip)
        )

    projects = []
    for row in cursor.fetchall():
        projects.append({
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "owner_id": row["owner_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        })

    return projects

# 获取项目详情


@router.get("/{project_id}", response_model=ProjectResponse, summary="获取项目详情")
async def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    获取项目详情

    参数:
    - project_id: 项目ID

    返回:
    - 项目详情
    """
    cursor = db.cursor()

    # 获取项目信息
    cursor.execute(
        """
        SELECT id, name, description, owner_id, created_at, updated_at
        FROM projects WHERE id = ?
        """,
        (project_id,)
    )
    project_data = cursor.fetchone()

    if not project_data:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 检查权限
    if not current_user.is_admin and project_data["owner_id"] != current_user.username:
        raise HTTPException(status_code=403, detail="没有权限访问此项目")

    return {
        "id": project_data["id"],
        "name": project_data["name"],
        "description": project_data["description"],
        "owner_id": project_data["owner_id"],
        "created_at": project_data["created_at"],
        "updated_at": project_data["updated_at"]
    }

# 更新项目


@router.put("/{project_id}", response_model=ProjectResponse, summary="更新项目")
async def update_project(
    project_id: int,
    project_update: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    更新项目信息

    参数:
    - project_id: 项目ID
    - project_update: 要更新的项目信息

    返回:
    - 更新后的项目信息
    """
    cursor = db.cursor()

    # 获取项目信息
    cursor.execute(
        "SELECT owner_id FROM projects WHERE id = ?",
        (project_id,)
    )
    project_data = cursor.fetchone()

    if not project_data:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 检查权限
    if not current_user.is_admin and project_data["owner_id"] != current_user.username:
        raise HTTPException(status_code=403, detail="没有权限编辑此项目")

    # 构建更新语句
    update_fields = []
    params = []

    if project_update.name is not None:
        update_fields.append("name = ?")
        params.append(project_update.name)

    if project_update.description is not None:
        update_fields.append("description = ?")
        params.append(project_update.description)

    if update_fields:
        update_fields.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(project_id)

        cursor.execute(
            f"""
            UPDATE projects
            SET {", ".join(update_fields)}
            WHERE id = ?
            """,
            tuple(params)
        )
    db.commit()

    # 获取更新后的项目
    cursor.execute(
        """
        SELECT id, name, description, owner_id, created_at, updated_at
        FROM projects WHERE id = ?
        """,
        (project_id,)
    )
    updated_project = cursor.fetchone()

    return {
        "id": updated_project["id"],
        "name": updated_project["name"],
        "description": updated_project["description"],
        "owner_id": updated_project["owner_id"],
        "created_at": updated_project["created_at"],
        "updated_at": updated_project["updated_at"]
    }

# 删除项目


@router.delete("/{project_id}", summary="删除项目")
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    删除项目

    参数:
    - project_id: 项目ID

    返回:
    - 删除成功的消息
    """
    cursor = db.cursor()

    # 获取项目信息
    cursor.execute(
        "SELECT owner_id FROM projects WHERE id = ?",
        (project_id,)
    )
    project_data = cursor.fetchone()

    if not project_data:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 检查权限
    if not current_user.is_admin and project_data["owner_id"] != current_user.username:
        raise HTTPException(status_code=403, detail="没有权限删除此项目")

    # 获取项目相关的图片
    cursor.execute(
        "SELECT file_path FROM images WHERE project_id = ?",
        (project_id,)
    )
    images = cursor.fetchall()

    # 删除图片文件
    for image in images:
        file_path = image["file_path"]
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"删除文件失败: {file_path}, 错误: {str(e)}")

    # 删除项目相关数据
    cursor.execute(
        "DELETE FROM text_to_image_generations WHERE project_id = ?", (project_id,))
    cursor.execute(
        "DELETE FROM image_to_image_generations WHERE project_id = ?", (project_id,))
    cursor.execute(
        "DELETE FROM image_generations WHERE project_id = ?", (project_id,))
    cursor.execute(
        "DELETE FROM images WHERE project_id = ?", (project_id,))
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    db.commit()

    return {"message": "项目已成功删除"}

# 获取项目图片


@router.get("/{project_id}/images")
async def get_project_images(
    project_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    username: str = Depends(verify_token)
):
    """获取项目下的所有图片"""
    try:
        with get_db() as db:
            cursor = db.cursor()

            # 检查用户是否有权限访问该项目
            cursor.execute(
                '''
                SELECT p.id FROM projects p
                LEFT JOIN project_users pu ON p.id = pu.project_id
                WHERE p.id = ? AND (p.owner_id = ? OR pu.user_id = ?)
                ''',
                (project_id, username, username)
            )

            project = cursor.fetchone()
            if not project:
                raise HTTPException(status_code=404, detail="项目不存在或无权访问")

            # 获取项目下的图片，只返回原始图片（非生成的图片）
            cursor.execute(
                '''
                SELECT * FROM images 
                WHERE project_id = ? AND (is_generated = 0 OR is_generated IS NULL)
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                ''',
                (project_id, limit, skip)
            )

            images = cursor.fetchall()
            return [dict(image) for image in images]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/images/count")
async def get_project_images_count(
    project_id: int,
    username: str = Depends(verify_token)
):
    """获取项目下的图片总数"""
    try:
        with get_db() as db:
            cursor = db.cursor()

            # 检查用户是否有权限访问该项目
            cursor.execute(
                '''
                SELECT p.id FROM projects p
                LEFT JOIN project_users pu ON p.id = pu.project_id
                WHERE p.id = ? AND (p.owner_id = ? OR pu.user_id = ?)
                ''',
                (project_id, username, username)
            )

            project = cursor.fetchone()
            if not project:
                raise HTTPException(status_code=404, detail="项目不存在或无权访问")

            # 获取项目下的原始图片数量（非生成的图片）
            cursor.execute(
                'SELECT COUNT(*) as total FROM images WHERE project_id = ? AND (is_generated = 0 OR is_generated IS NULL)',
                (project_id,)
            )

            result = cursor.fetchone()
            return {"total": result['total']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 辅助函数：尝试多种编码组合解码文件名


def try_decode_filename(original_filename: str, is_windows: bool) -> str:
    """尝试多种编码组合解码文件名"""
    # 检查是否已经是有效的UTF-8字符串
    try:
        # 如果能成功编码为UTF-8，说明原始文件名已经是UTF-8编码
        original_filename.encode('utf-8').decode('utf-8')
        # 检查是否包含常见乱码特征
        if not re.search(r'[鏆傛棤鍥剧墖σ__Σ_í]', original_filename):
            return original_filename
    except UnicodeError:
        pass  # 不是有效的UTF-8，继续尝试其他编码

    # 首先尝试cp437->utf-8编码组合，这对于"图标/icons8-微信-500.png"这样的路径效果最好
    try:
        decoded = original_filename.encode(
            'cp437').decode('utf-8', errors='replace')
        # 如果解码后包含中文字符，并且不包含常见乱码特征，直接返回结果
        if re.search(r'[\u4e00-\u9fff]', decoded) and not re.search(r'[鏆傛棤鍥剧墖σ__Σ_í]', decoded):
            print(f"使用cp437->utf-8成功解码: {decoded}")
            return decoded
    except Exception as e:
        print(f"cp437->utf-8解码失败: {str(e)}")

    # 定义可能的编码组合
    encoding_pairs = [
        ('cp437', 'utf-8'),  # 标准ZIP编码到UTF-8
        ('cp437', 'gbk'),    # 标准ZIP编码到GBK（中文Windows常用）
        ('cp437', 'big5'),   # 标准ZIP编码到Big5（繁体中文常用）
        ('latin1', 'utf-8'),  # Latin1到UTF-8
        ('gbk', 'utf-8'),    # GBK到UTF-8
    ]

    # Windows系统优先尝试GBK编码
    if is_windows:
        encoding_pairs.insert(0, ('cp437', 'gbk'))
    else:
        # macOS/Unix系统优先尝试UTF-8编码
        encoding_pairs.insert(0, ('cp437', 'utf-8'))

    # 尝试所有编码组合
    best_filename = original_filename
    best_score = 0

    for src_encoding, dest_encoding in encoding_pairs:
        try:
            decoded = original_filename.encode(src_encoding).decode(
                dest_encoding, errors='replace')
            # 评分标准：中文字符数量、特殊字符数量（越少越好）
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', decoded))
            special_chars = len(re.findall(
                r'[^\w\.\-\u4e00-\u9fff/]', decoded))  # 允许路径分隔符
            weird_chars = len(re.findall(r'[鏆傛棤鍥剧墖σ__Σ_í]', decoded))

            # 计算得分：中文字符加分，特殊字符和怪异字符减分
            score = chinese_chars * 2 - special_chars - weird_chars * 3

            print(f"尝试 {src_encoding}->{dest_encoding}: {decoded} (得分: {score})")

            if score > best_score:
                best_score = score
                best_filename = decoded
        except Exception as e:
            print(f"编码 {src_encoding}->{dest_encoding} 失败: {str(e)}")

    # 如果所有编码尝试都失败，使用原始文件名
    if best_score <= 0:
        print(f"所有编码尝试均未产生更好的结果，使用原始文件名")
        return original_filename

    print(f"最佳解码结果: {best_filename} (得分: {best_score})")
    return best_filename

# 辅助函数：计算文件的MD5哈希值


def calculate_file_md5(file_path: str) -> str:
    """计算文件的MD5哈希值"""
    try:
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            # 读取文件块并更新哈希值
            for byte_block in iter(lambda: f.read(4096), b""):
                md5_hash.update(byte_block)
        return md5_hash.hexdigest()
    except Exception as e:
        print(f"计算文件MD5失败: {str(e)}")
        return ""

# 修改文件夹上传处理逻辑


@router.post("/{project_id}/upload", summary="上传图片到项目")
async def upload_images(
    project_id: int,
    files: List[UploadFile] = File(...),
    upload_type: str = Form("single"),  # single, folder, zip
    username: str = Depends(verify_token)
):
    """
    上传图片到项目

    参数:
    - project_id: 项目ID
    - files: 上传的图片文件列表
    - upload_type: 上传类型，可选值：single(单张图片), folder(文件夹), zip(压缩包)

    返回:
    - 上传结果
    """
    try:
        # 检查项目是否存在
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute(
                '''
                SELECT p.id FROM projects p
                LEFT JOIN project_users pu ON p.id = pu.project_id
                WHERE p.id = ? AND (p.owner_id = ? OR pu.user_id = ?)
                ''',
                (project_id, username, username)
            )

            project = cursor.fetchone()
            if not project:
                raise HTTPException(status_code=404, detail="项目不存在或无权访问")

            # 创建项目图片目录
            upload_dir = os.path.join(
                settings.UPLOAD_DIR, f"projects/{project_id}")
            os.makedirs(upload_dir, exist_ok=True)

            uploaded_images = []
            processed_files = set()  # 用于跟踪已处理的文件，避免重复处理

            # 处理不同类型的上传
            if upload_type == "single":
                # 单张图片上传
                for file in files:
                    # 跳过已处理的文件
                    if file.filename in processed_files:
                        print(f"跳过重复文件: {file.filename}")
                        continue

                    processed_files.add(file.filename)
                    image_path = await save_image(file, upload_dir, file.filename)
                    if image_path:
                        # 检查数据库中是否已存在相同路径的图片
                        cursor.execute(
                            "SELECT id FROM images WHERE file_path = ? AND project_id = ?",
                            (image_path, project_id)
                        )
                        existing_image = cursor.fetchone()
                        if existing_image:
                            print(f"文件已存在于数据库中，跳过: {image_path}")
                            image_data = get_image_data(
                                cursor, existing_image["id"])
                            if image_data:
                                uploaded_images.append(image_data)
                            continue

                        image_id = save_image_to_db(
                            cursor, db, image_path, file.content_type, project_id)
                        image_data = get_image_data(cursor, image_id)
                        if image_data:
                            uploaded_images.append(image_data)

            elif upload_type == "folder":
                # 文件夹上传 (前端会将文件夹中的文件作为多个文件上传)
                # 这里我们需要处理可能的文件名冲突
                existing_files = set()

                # 获取项目中已有的图片文件路径和MD5哈希值
                cursor.execute(
                    "SELECT id, file_path, file_size FROM images WHERE project_id = ?",
                    (project_id,)
                )
                existing_db_files = {}
                for row in cursor.fetchall():
                    existing_db_files[row["file_path"]] = {
                        "id": row["id"],
                        "size": row["file_size"]
                    }

                # 计算现有文件的MD5哈希值（仅在需要时计算）
                file_md5_cache = {}

                for file in files:
                    # 跳过已处理的文件
                    if file.filename in processed_files:
                        print(f"跳过重复文件: {file.filename}")
                        continue

                    processed_files.add(file.filename)

                    # 检查是否为图片文件
                    if is_image_file(file.filename):
                        # 处理文件名冲突
                        filename = get_unique_filename(
                            file.filename, existing_files)
                        existing_files.add(filename)

                        # 构建目标文件路径
                        target_path = os.path.join(upload_dir, filename)

                        # 检查该文件是否已经存在于数据库中（通过路径）
                        if target_path in existing_db_files:
                            print(f"文件路径已存在于数据库中: {target_path}")

                            # 获取文件大小进行比较
                            file_content = await file.read()
                            file_size = len(file_content)
                            file.file.seek(0)  # 重置文件指针

                            if file_size == existing_db_files[target_path]["size"]:
                                print(f"文件大小相同，跳过上传")
                                image_data = get_image_data(
                                    cursor, existing_db_files[target_path]["id"])
                                if image_data:
                                    uploaded_images.append(image_data)
                                continue

                        # 保存文件
                        image_path = await save_image(file, upload_dir, filename)
                        if image_path:
                            # 计算文件MD5哈希值
                            file_md5 = calculate_file_md5(image_path)

                            # 检查是否有相同MD5的文件
                            is_duplicate = False
                            for db_path, info in existing_db_files.items():
                                if db_path not in file_md5_cache:
                                    file_md5_cache[db_path] = calculate_file_md5(
                                        db_path)

                                if file_md5 and file_md5 == file_md5_cache[db_path]:
                                    print(
                                        f"发现内容相同的文件: {image_path} 与 {db_path}")
                                    # 删除刚保存的文件
                                    try:
                                        os.remove(image_path)
                                        print(f"删除重复文件: {image_path}")
                                    except Exception as e:
                                        print(f"删除文件失败: {str(e)}")

                                    # 使用已存在的图片记录
                                    image_data = get_image_data(
                                        cursor, info["id"])
                                    if image_data:
                                        uploaded_images.append(image_data)
                                    is_duplicate = True
                                    break

                            if not is_duplicate:
                                # 保存到数据库
                                image_id = save_image_to_db(
                                    cursor, db, image_path, file.content_type, project_id)
                                image_data = get_image_data(cursor, image_id)
                                if image_data:
                                    uploaded_images.append(image_data)
                                    # 更新缓存
                                    existing_db_files[image_path] = {
                                        "id": image_id,
                                        "size": os.path.getsize(image_path)
                                    }
                                    file_md5_cache[image_path] = file_md5

            elif upload_type == "zip":
                # 压缩包上传
                if len(files) != 1:
                    raise HTTPException(
                        status_code=400, detail="压缩包上传只能上传一个文件")

                # 处理zip文件上传逻辑
                pass
            else:
                raise HTTPException(status_code=400, detail="不支持的上传类型")

            return {"message": "上传成功", "results": uploaded_images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 辅助函数：保存图片文件


async def save_image(file: UploadFile, upload_dir: str, filename: str) -> str:
    """保存上传的图片文件"""
    # 确保上传目录存在
    os.makedirs(upload_dir, exist_ok=True)
    
    # 构建文件路径
    file_path = os.path.join(upload_dir, filename)
    
    # 保存上传的文件
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
    
    # 使用 FFmpeg 处理和验证图片
    try:
        # 创建临时输出文件路径
        file_name, file_ext = os.path.splitext(filename)
        temp_output = os.path.join(upload_dir, f"temp_{file_name}{file_ext}")
        
        # 运行 FFmpeg 命令处理图片
        process = await asyncio.create_subprocess_exec(
            'ffmpeg', '-i', file_path, '-y', temp_output,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        print(f"使用 ffmpeg 处理图片: {file_path}")
        # 检查处理结果
        if process.returncode != 0:
            # 如果处理失败，删除原文件并抛出异常
            os.remove(file_path)
            raise Exception(f"图片验证失败: {stderr.decode()}")
            
        # 处理成功后，用处理后的图片替换原图片
        os.replace(temp_output, file_path)
    except Exception as e:
        # 确保清理任何临时文件
        if os.path.exists(file_path):
            os.remove(file_path)
        if 'temp_output' in locals() and os.path.exists(temp_output):
            os.remove(temp_output)
        raise Exception(f"FFmpeg 处理失败: {str(e)}")
    
    return file_path

# 辅助函数：保存图片信息到数据库


def save_image_to_db(cursor, db, file_path: str, file_type: str, project_id: int) -> int:
    """保存图片信息到数据库"""
    try:
        file_size = os.path.getsize(file_path)
        now = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO images (file_path, file_size, file_type, project_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (file_path, file_size, file_type, project_id, now)
        )
        db.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"保存图片信息到数据库失败: {str(e)}")
        return None

# 辅助函数：获取图片数据


def get_image_data(cursor, image_id: int) -> dict:
    """获取图片数据"""
    try:
        cursor.execute(
            """
            SELECT id, file_path, file_size, file_type, width, height, project_id, created_at
            FROM images WHERE id = ?
            """,
            (image_id,)
        )
        image_data = cursor.fetchone()
        if image_data:
            return {
                "id": image_data["id"],
                "file_path": image_data["file_path"],
                "file_size": image_data["file_size"],
                "file_type": image_data["file_type"],
                "width": image_data["width"],
                "height": image_data["height"],
                "project_id": image_data["project_id"],
                "created_at": image_data["created_at"]
            }
        return None
    except Exception as e:
        print(f"获取图片数据失败: {str(e)}")
        return None

# 辅助函数：检查是否为图片文件


def is_image_file(filename: str) -> bool:
    """检查文件是否为图片"""
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    return any(filename.lower().endswith(ext) for ext in image_extensions)

# 辅助函数：获取唯一文件名


def get_unique_filename(filename: str, existing_files: set) -> str:
    """获取唯一文件名，避免冲突"""
    # 处理文件名编码问题
    try:
        # 移除可能导致问题的特殊字符
        safe_filename = re.sub(r'[^\w\.\-\u4e00-\u9fa5]', '_', filename)

        # 确保文件名是有效的UTF-8编码
        safe_filename = safe_filename.encode('utf-8').decode('utf-8')

        if safe_filename not in existing_files:
            return safe_filename

        # 如果文件名已存在，添加下划线和序号
        name, ext = os.path.splitext(safe_filename)
        counter = 1
        while f"{name}_{counter}{ext}" in existing_files:
            counter += 1

        return f"{name}_{counter}{ext}"
    except Exception as e:
        print(f"处理文件名失败: {str(e)}")
        # 如果处理中文名失败，使用时间戳作为文件名
        timestamp_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}{os.path.splitext(filename)[1]}"
        return timestamp_filename

# 辅助函数：获取文件类型


def get_file_type(filename: str) -> str:
    """根据文件扩展名获取文件类型"""
    ext = os.path.splitext(filename)[1].lower()
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.webp': 'image/webp'
    }
    return mime_types.get(ext, 'application/octet-stream')


@router.delete("/{project_id}/images/{image_id}", summary="删除项目图片")
async def delete_project_image(
    project_id: int,
    image_id: int,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    删除项目中的图片及其生成的图片

    参数:
    - project_id: 项目ID
    - image_id: 图片ID

    返回:
    - 删除成功的消息
    """
    cursor = db.cursor()

    # 获取项目信息
    cursor.execute(
        "SELECT owner_id FROM projects WHERE id = ?",
        (project_id,)
    )
    project_data = cursor.fetchone()

    if not project_data:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 检查权限
    if not current_user.is_admin and project_data["owner_id"] != current_user.username:
        raise HTTPException(status_code=403, detail="没有权限删除此项目的图片")

    # 获取图片信息
    cursor.execute(
        "SELECT file_path FROM images WHERE id = ? AND project_id = ?",
        (image_id, project_id)
    )
    image_data = cursor.fetchone()

    if not image_data:
        raise HTTPException(status_code=404, detail="图片不存在或不属于该项目")

    file_path = image_data["file_path"]

    # 查找所有基于此图片生成的图片
    cursor.execute(
        """
        SELECT i.id, i.file_path 
        FROM images i
        JOIN image_generations g ON i.id = g.result_image_id
        WHERE g.source_image_id = ?
        """,
        (image_id,)
    )
    generated_images = cursor.fetchall()

    # 删除生成的图片文件
    for gen_image in generated_images:
        gen_file_path = gen_image["file_path"]
        if os.path.exists(gen_file_path):
            try:
                os.remove(gen_file_path)
                print(f"已删除生成图片文件: {gen_file_path}")
            except Exception as e:
                print(f"删除生成图片文件失败: {gen_file_path}, 错误: {str(e)}")

    # 删除原始图片文件
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"已删除原始图片文件: {file_path}")
        except Exception as e:
            print(f"删除原始图片文件失败: {file_path}, 错误: {str(e)}")

    # 开始事务
    try:
        # 删除所有相关的生成历史记录
        # 1. 删除text_to_image_generations表中的记录
        cursor.execute(
            "DELETE FROM text_to_image_generations WHERE image_id = ?",
            (image_id,)
        )

        # 2. 删除image_to_image_generations表中的记录
        cursor.execute(
            "DELETE FROM image_to_image_generations WHERE prompt_image_id = ? OR result_image_id = ?",
            (image_id, image_id)
        )

        # 3. 删除统一的image_generations表中的记录
        cursor.execute(
            "DELETE FROM image_generations WHERE source_image_id = ? OR result_image_id = ?",
            (image_id, image_id)
        )

        # 4. 删除生成图片的记录
        for gen_image in generated_images:
            # 删除生成图片在image_generations表中的记录
            cursor.execute(
                "DELETE FROM image_generations WHERE result_image_id = ?",
                (gen_image["id"],)
            )

            # 删除生成图片在images表中的记录
            cursor.execute(
                "DELETE FROM images WHERE id = ?",
                (gen_image["id"],)
            )

        # 5. 最后删除原始图片记录
        cursor.execute(
            "DELETE FROM images WHERE id = ?",
            (image_id,)
        )

        # 提交事务
        db.commit()

        return {"message": "图片及其生成图片已成功删除"}
    except Exception as e:
        # 发生错误时回滚事务
        db.rollback()
        print(f"删除图片记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除图片记录失败: {str(e)}")

@router.get("/{project_id}/tasks")
async def check_project_tasks(
    project_id: int,
    username: str = Depends(verify_token),
    db = Depends(get_db)
):
    """检查项目是否有运行中的任务"""
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM batch_tasks 
            WHERE project_id = ? AND status IN ('pending', 'processing')
        """, (project_id,))
        result = cursor.fetchone()
        
        return {"has_running_task": result['count'] > 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch-generate/{project_id}")
async def create_batch_generation(
    project_id: int,
    request: BatchGenerationRequest,
    username: str = Depends(verify_token),
    db = Depends(get_db)
):
    """创建批量生成任务"""
    cursor = db.cursor()
    try:
        # 检查是否存在未完成的任务
        cursor.execute("""
            SELECT id FROM batch_tasks 
            WHERE project_id = ? AND status IN ('pending', 'processing')
        """, (project_id,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="该项目已存在未完成的批量任务")
        
        # 获取项目信息和权限验证
        cursor.execute(
            "SELECT * FROM projects WHERE id = ? AND owner_id = ?", 
            (project_id, username)
        )
        project = cursor.fetchone()
        
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在或无权访问")

        # 获取项目中的所有未生成的图片
        cursor.execute(
            "SELECT * FROM images WHERE project_id = ? AND is_generated = 0",
            (project_id,)
        )
        images = cursor.fetchall()
        
        if not images:
            raise HTTPException(status_code=400, detail="项目中没有可生成的图片")

        # 创建批量任务
        cursor.execute("""
            INSERT INTO batch_tasks (
                project_id, user_id, total_images, model_id, prompt, status
            ) VALUES (?, ?, ?, ?, ?, 'pending')
            RETURNING id
        """, (
            project_id, 
            username, 
            len(images) * 3,  # 每张图片生成3个版本
            request.model_id, 
            request.prompt
        ))
        task_id = cursor.fetchone()[0]
        
        # 创建子任务
        for image in images:
            for _ in range(3):  # 每张图片生成3个版本
                seed = random.randint(1, 999999999)
                cursor.execute("""
                    INSERT INTO batch_task_details (
                        batch_task_id, source_image_id, seed
                    ) VALUES (?, ?, ?)
                """, (task_id, image['id'], seed))
        
        db.commit()
        
        # 启动后台处理进程
        # 修改这里，使用正确的数据库路径
        asyncio.create_task(process_batch_task(task_id, settings.DATABASE_PATH))
        
        return {
            "task_id": task_id,
            "status": "pending",
            "total_images": len(images) * 3,
            "completed_images": 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error("创建批量任务失败", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
