#!/bin/bash

# 设置环境变量以解决MacOS的fork问题
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# 停止所有现有worker进程
echo "停止现有的worker进程..."
pkill -f "python worker.py"

# 等待进程完全停止
sleep 2

# 删除之前的日志文件
echo "清理日志文件..."
rm -f worker.log

# 启动worker进程
echo "启动新的worker进程..."
python worker.py --concurrency=3 &

# 输出日志文件
echo "Worker进程已启动，日志将显示在下面:"
echo "-----------------------------------"
sleep 2
tail -f worker.log 