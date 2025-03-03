#!/bin/bash

# 队列工作进程停止脚本

# 检查PID文件
PID_FILE="queue_worker.pid"
if [ ! -f "$PID_FILE" ]; then
    echo "未找到PID文件，队列工作进程可能未运行"
    exit 1
fi

# 读取PID
PID=$(cat "$PID_FILE")

# 检查进程是否存在
if ! ps -p $PID > /dev/null; then
    echo "PID为 $PID 的进程不存在，可能已经停止"
    rm -f "$PID_FILE"
    exit 0
fi

# 发送终止信号
echo "正在停止队列工作进程 (PID: $PID)..."
kill $PID

# 等待进程终止
MAX_WAIT=30
COUNT=0
while ps -p $PID > /dev/null && [ $COUNT -lt $MAX_WAIT ]; do
    echo "等待进程终止... ($COUNT/$MAX_WAIT)"
    sleep 1
    COUNT=$((COUNT+1))
done

# 检查进程是否已终止
if ps -p $PID > /dev/null; then
    echo "进程未在 $MAX_WAIT 秒内终止，尝试强制终止..."
    kill -9 $PID
    sleep 2
fi

# 最终检查
if ps -p $PID > /dev/null; then
    echo "无法终止进程，请手动检查: kill -9 $PID"
    exit 1
else
    echo "队列工作进程已停止"
    rm -f "$PID_FILE"
    exit 0
fi 