# 图像生成后端服务

这是一个基于FastAPI的图像生成后端服务，支持单个和批量图像生成，并使用Redis队列进行任务管理。

## 主要功能

- 支持单个图像生成
- 支持批量图像生成，使用Redis队列管理任务
- 可配置并发处理数量
- 提供队列状态查询和取消功能
- 异步处理图像生成任务

## 技术栈

- FastAPI: Web框架
- Redis: 队列和缓存存储
- RQ (Redis Queue): 后台任务处理
- Docker & Docker Compose: 容器化和服务编排

## 项目结构

```
backend/
├── app/
│   ├── core/           # 核心功能（配置、认证等）
│   ├── models/         # 数据模型
│   ├── routers/        # API路由
│   ├── services/       # 业务逻辑服务
│   │   ├── image_service.py  # 图像处理服务
│   │   └── queue/      # 队列服务
│   │       ├── queue_service.py  # 队列管理服务
│   │       └── worker.py         # 任务处理工作进程
│   └── main.py         # 应用入口
├── worker.py           # 工作进程启动脚本
├── requirements.txt    # 依赖项
├── Dockerfile          # API服务的Docker配置
├── Dockerfile.worker   # 工作进程的Docker配置
└── docker-compose.yml  # Docker Compose配置
```

## 快速开始

### 前提条件

- Docker和Docker Compose
- Python 3.9+（非Docker环境）

### 使用Docker部署

1. 克隆仓库

```bash
git clone <repo-url>
cd <repo-directory>/backend
```

2. 启动服务

```bash
docker-compose up -d
```

这将启动三个服务：
- Redis服务器
- API服务（FastAPI应用）
- 工作进程服务（处理队列任务）

### 手动运行（开发环境）

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 启动Redis（如果尚未运行）

```bash
# 可以使用Docker单独运行Redis
docker run -d -p 6379:6379 redis
```

3. 启动API服务

```bash
uvicorn app.main:app --reload
```

4. 启动工作进程（新的终端窗口）

```bash
python worker.py --concurrency=3
```

## 注意事项

### 工作进程启动

工作进程使用 RQ (Redis Queue) 库处理任务。根据您安装的 RQ 版本，启动命令可能会略有不同。当前实现适用于 RQ 4.5.1 版本，如果您使用其他版本可能需要调整代码。

如果在启动工作进程时遇到 `work() got an unexpected keyword argument 'name'` 错误，这是因为您的 RQ 版本不支持在 `work()` 方法中使用 `name` 参数。这个问题已在当前版本中修复。

### 异步处理

本项目中的 `ImageService` 使用了 FastAPI 的异步处理能力，而 RQ 工作进程是同步的。为了解决这个兼容性问题，工作进程中使用了 `asyncio.new_event_loop()` 和 `loop.run_until_complete()` 来处理异步函数调用。

如果您遇到 `'coroutine' object does not support item assignment` 错误，这表明您正在尝试直接使用异步函数的返回值而没有 `await` 它。检查 `worker.py` 中的代码，确保异步函数调用使用了 `loop.run_until_complete()`。

### 队列监控

您可以通过 API 端点或直接通过 Redis 客户端监控队列状态。系统会自动清理过期的队列数据（默认保留24小时）。

## API端点

### 图像生成

- `GET /history` - 获取用户的图像生成历史
- `POST /create-queue` - 创建图像生成队列
- `GET /queue-status/{queue_id}` - 获取队列状态
- `POST /cancel-queue/{queue_id}` - 取消队列
- `GET /active-queues` - 获取用户的所有活跃队列

## 配置

可以通过环境变量配置以下参数：

- `REDIS_HOST` - Redis服务器主机名（默认：localhost）
- `REDIS_PORT` - Redis服务器端口（默认：6379）
- `REDIS_DB` - Redis数据库索引（默认：0）

## 许可证

[您的许可证信息] 