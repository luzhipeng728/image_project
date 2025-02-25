# 图片生成服务

这是一个基于React和FastAPI的图片生成服务，提供用户认证、图片生成等功能。

## 项目结构

```
.
├── frontend/          # React前端项目
│   ├── public/       # 静态资源
│   ├── src/          # 源代码
│   └── package.json  # 依赖配置
└── backend/          # FastAPI后端项目
    ├── app/          # 应用代码
    └── requirements.txt  # Python依赖
```

## 开发环境要求

- Node.js 14+
- Python 3.8+
- npm 或 yarn

## 安装和运行

### 前端

```bash
cd frontend
npm install
npm start
```

前端服务将在 http://localhost:3000 运行

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app/main.py
```

后端API将在 http://localhost:8000 运行

## API文档

启动后端服务后，可以访问 http://localhost:8000/docs 查看API文档。

## 主要功能

1. 用户认证
   - 注册
   - 登录
   - JWT认证

2. 图片生成
   - 支持多个模型
   - 自定义生成参数
   - 历史记录查看

3. 模型管理
   - 模型列表
   - 模型信息 