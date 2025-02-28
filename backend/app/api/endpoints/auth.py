from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from typing import List

from ...core.auth import create_access_token, get_password_hash, verify_password, get_current_user
from ...schemas.schemas import UserCreate, Token, UserResponse, UserAdminUpdate
from ...database.database import get_db
from ...models.models import User

router = APIRouter()


@router.post("/register", response_model=dict)
async def register(user: UserCreate):
    db = get_db()
    cursor = db.cursor()

    try:
        # 检查用户是否已存在
        cursor.execute(
            'SELECT username FROM users WHERE username = ?', (user.username,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=400, detail="Username already registered")

        # 创建新用户
        hashed_password = get_password_hash(user.password)
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                       (user.username, hashed_password))
        db.commit()
        return {"message": "User registered successfully"}
    finally:
        db.close()


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = get_db()
    cursor = db.cursor()

    try:
        # 查找用户
        cursor.execute(
            'SELECT username, password FROM users WHERE username = ?', (form_data.username,))
        user = cursor.fetchone()

        if not user:
            raise HTTPException(status_code=400, detail="用户名或密码错误")

        if not verify_password(form_data.password, user[1]):  # user[1] 是密码
            raise HTTPException(status_code=400, detail="用户名或密码错误")

        access_token = create_access_token({"sub": user[0]})  # user[0] 是用户名
        return {"access_token": access_token, "token_type": "bearer"}
    finally:
        db.close()


@router.get("/users", response_model=List[UserResponse], summary="获取用户列表")
async def get_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """
    获取系统中的用户列表

    参数:
    - skip: 跳过的记录数，用于分页
    - limit: 返回的最大记录数，用于分页

    返回:
    - 用户列表

    注意:
    - 需要管理员权限
    """
    # 检查是否为管理员
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="只有管理员可以查看用户列表")

    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT username, created_at, is_admin
            FROM users
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, skip)
        )

        users = []
        for row in cursor.fetchall():
            users.append({
                "username": row["username"],
                "created_at": row["created_at"],
                "is_admin": bool(row["is_admin"])
            })

        return users
    finally:
        db.close()


@router.put("/users/{username}/admin", response_model=UserResponse, summary="设置用户管理员权限")
async def set_user_admin(
    username: str,
    user_update: UserAdminUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    设置用户的管理员权限

    参数:
    - username: 要设置的用户名
    - user_update: 包含is_admin字段的请求体

    返回:
    - 更新后的用户信息

    注意:
    - 需要管理员权限
    """
    # 检查是否为管理员
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只有管理员可以设置用户权限")

    db = get_db()
    try:
        cursor = db.cursor()

        # 检查用户是否存在
        cursor.execute(
            "SELECT username FROM users WHERE username = ?",
            (username,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="用户不存在")

        # 更新用户权限
        cursor.execute(
            "UPDATE users SET is_admin = ? WHERE username = ?",
            (user_update.is_admin, username)
        )
        db.commit()

        # 获取更新后的用户信息
        cursor.execute(
            "SELECT username, created_at, is_admin FROM users WHERE username = ?",
            (username,)
        )
        user_data = cursor.fetchone()

        return {
            "username": user_data["username"],
            "created_at": user_data["created_at"],
            "is_admin": bool(user_data["is_admin"])
        }
    finally:
        db.close()


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户的信息

    返回:
    - 当前用户信息
    """
    return {
        "username": current_user.username,
        "created_at": current_user.created_at,
        "is_admin": current_user.is_admin
    }
