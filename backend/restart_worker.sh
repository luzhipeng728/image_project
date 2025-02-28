#!/bin/bash

# 设置环境变量以解决MacOS的fork问题
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

echo "正在检查当前运行的worker进程..."
WORKER_COUNT=$(ps aux | grep "python worker.py" | grep -v grep | wc -l)
echo "发现 $WORKER_COUNT 个worker进程正在运行"

# 停止所有现有worker进程
echo "停止现有的worker进程..."
pkill -f "python worker.py"

# 等待进程完全停止
sleep 2

# 保存旧的日志文件
if [ -f "worker.log" ]; then
    echo "备份旧的日志文件..."
    mv worker.log worker.log.$(date +%Y%m%d%H%M%S)
fi

# 清理Redis中的worker注册信息
echo "清理Redis中的旧worker注册信息..."
redis-cli keys "rq:worker:*" | xargs -r redis-cli del > /dev/null 2>&1

# 启动worker进程
echo "启动新的worker进程..."
python worker.py --concurrency=3 > worker_startup.log 2>&1 &

# 等待worker启动
sleep 2

# 检查worker是否正常启动
if pgrep -f "python worker.py" > /dev/null; then
    echo "Worker进程已成功启动！"
    
    # 获取当前目录的绝对路径
    CURRENT_DIR=$(pwd)
    
    echo "====================================================="
    echo "Worker日志信息："
    echo "1. 日志文件位置: $CURRENT_DIR/worker.log"
    echo "2. 查看日志命令: tail -f $CURRENT_DIR/worker.log"
    echo
    echo "注意：请确保在backend目录中执行此命令"
    echo "如果在项目根目录，请使用: tail -f backend/worker.log"
    echo "====================================================="
    echo
    echo "Redis队列状态查询命令:"
    echo "redis-cli keys \"image_generation_*\""
    echo "redis-cli keys \"queue:image_generation_*:info\""
    echo
    echo "如需查看worker进程状态，可以使用:"
    echo "ps aux | grep \"python worker.py\" | grep -v grep"
else
    echo "Worker进程启动失败，请检查worker_startup.log文件了解详情"
fi 