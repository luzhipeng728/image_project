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

# 使用更可靠的方式启动worker进程
echo "启动新的worker进程，并发数:5..."

# 在当前目录创建一个启动器脚本
cat > worker_launcher.sh << 'EOL'
#!/bin/bash
# 设置环境变量以解决MacOS的fork问题
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
cd "$(dirname "$0")"
exec python worker.py --concurrency=5 >> worker.log 2>&1
EOL

# 给启动器脚本添加执行权限
chmod +x worker_launcher.sh

# 使用nohup启动进程，确保它在后台运行
nohup ./worker_launcher.sh > /dev/null 2>&1 &

# 记录主进程ID
WORKER_PID=$!
echo "Worker进程已以PID $WORKER_PID 启动"

# 等待进程启动
sleep 5

# 检查worker是否正常启动
if pgrep -f "python worker.py" > /dev/null; then
    echo "Worker进程已成功启动！"
    
    # 获取进程列表
    echo "运行中的Worker进程:"
    ps aux | grep "python worker.py" | grep -v grep
    
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
    echo "Worker进程启动失败，请检查worker.log文件了解详情"
fi 