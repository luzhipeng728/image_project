from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm

from ...core.auth import create_access_token, get_password_hash, verify_password
from ...schemas.schemas import UserCreate, Token
from ...database.database import get_db

router = APIRouter()

@router.post("/register", response_model=dict)
async def register(user: UserCreate):
    with get_db() as db:
        cursor = db.cursor()
        
        # 检查用户是否已存在
        cursor.execute('SELECT username FROM users WHERE username = ?', (user.username,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Username already registered")
        
        # 创建新用户
        hashed_password = get_password_hash(user.password)
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                      (user.username, hashed_password))
        db.commit()
        return {"message": "User registered successfully"}

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    with get_db() as db:
        cursor = db.cursor()
        
        # 查找用户
        cursor.execute('SELECT username, password FROM users WHERE username = ?', (form_data.username,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=400, detail="用户名或密码错误")
        
        if not verify_password(form_data.password, user[1]):  # user[1] 是密码
            raise HTTPException(status_code=400, detail="用户名或密码错误")
        
        access_token = create_access_token({"sub": user[0]})  # user[0] 是用户名
        return {"access_token": access_token, "token_type": "bearer"} 