#!/bin/bash

# 队列工作进程启动脚本

# 设置环境变量
export PYTHONPATH=$(pwd)

# 默认并发数
CONCURRENCY=3

# 解析命令行参数
while [[ $# -gt 0 ]]; do
  case $1 in
    --concurrency=*)
      CONCURRENCY="${1#*=}"
      shift
      ;;
    *)
      echo "未知参数: $1"
      exit 1
      ;;
  esac
done

# 检查是否已有进程在运行
PID_FILE="queue_worker.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null; then
        echo "队列工作进程已在运行，PID: $PID"
        echo "如需重启，请先停止现有进程: kill $PID"
        exit 1
    else
        echo "发现过期的PID文件，将被覆盖"
    fi
fi

# 启动队列工作进程
echo "启动队列工作进程，并发数: $CONCURRENCY"
nohup python queue_worker.py --concurrency=$CONCURRENCY > queue_worker.out 2>&1 &

# 保存PID
echo $! > "$PID_FILE"
echo "队列工作进程已启动，PID: $!"
echo "日志输出重定向到 queue_worker.out"
echo "使用 'tail -f queue_worker.out' 查看实时日志" 