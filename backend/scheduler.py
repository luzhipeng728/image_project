import subprocess
import time
import os
import signal
import sys
import sqlite3
import json
import psutil

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect('your_database.db')  # 替换为你的数据库路径
    conn.row_factory = sqlite3.Row
    return conn

def is_process_running(project_id):
    """检查指定项目的worker进程是否已经在运行"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == 'python' and len(proc.info['cmdline']) >= 4:
                if 'worker.py' in proc.info['cmdline'] and str(project_id) in proc.info['cmdline']:
                    return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return None

def get_progress(project_id):
    """获取项目处理进度"""
    db = get_db()
    cursor = db.cursor()
    
    # 获取总任务数
    cursor.execute("SELECT COUNT(*) FROM images WHERE project_id = ?", (project_id,))
    total = cursor.fetchone()[0]
    
    # 获取已完成任务数
    cursor.execute("SELECT COUNT(*) FROM images WHERE project_id = ? AND is_generated = 1", (project_id,))
    completed = cursor.fetchone()[0]
    
    # 获取最近处理的任务
    cursor.execute("""
        SELECT id, file_path, created_at 
        FROM images 
        WHERE project_id = ? AND is_generated = 1 
        ORDER BY id DESC LIMIT 1
    """, (project_id,))
    last_processed = cursor.fetchone()
    
    db.close()
    
    progress = {
        "project_id": project_id,
        "total_tasks": total,
        "completed_tasks": completed,
        "progress_percentage": (completed / total * 100) if total > 0 else 0,
        "last_processed": dict(last_processed) if last_processed else None
    }
    
    return progress

def start_worker(project_id, prompt, model_id):
    """启动worker进程并捕获输出"""
    # 检查是否已有相同项目的进程在运行
    existing_pid = is_process_running(project_id)
    if existing_pid:
        print(f"项目 {project_id} 的worker进程已在运行 (PID: {existing_pid})")
        return existing_pid
    
    # 启动新的worker进程
    process = subprocess.Popen(
        ["python", "worker.py", str(project_id), prompt, str(model_id)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    print(f"已启动项目 {project_id} 的worker进程 (PID: {process.pid})")
    
    # 创建日志文件
    log_file = f"worker_{project_id}.log"
    with open(log_file, "w") as f:
        f.write(f"Worker进程启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"命令: python worker.py {project_id} \"{prompt}\" {model_id}\n\n")
    
    # 启动线程来读取输出
    def log_output(stream, prefix, log_file):
        for line in stream:
            print(f"{prefix}: {line.strip()}")
            with open(log_file, "a") as f:
                f.write(f"{prefix}: {line}")
    
    import threading
    stdout_thread = threading.Thread(target=log_output, args=(process.stdout, "输出", log_file))
    stderr_thread = threading.Thread(target=log_output, args=(process.stderr, "错误", log_file))
    
    stdout_thread.daemon = True
    stderr_thread.daemon = True
    
    stdout_thread.start()
    stderr_thread.start()
    
    return process.pid

def stop_worker(project_id):
    """停止指定项目的worker进程"""
    pid = is_process_running(project_id)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"已停止项目 {project_id} 的worker进程 (PID: {pid})")
            return True
        except Exception as e:
            print(f"停止进程失败: {e}")
            return False
    else:
        print(f"未找到项目 {project_id} 的worker进程")
        return False

def monitor_progress(project_id, interval=5):
    """监控项目处理进度"""
    try:
        while True:
            # 检查进程是否还在运行
            pid = is_process_running(project_id)
            if not pid:
                print(f"项目 {project_id} 的worker进程已结束")
                
                # 检查日志文件
                log_file = f"worker_{project_id}.log"
                if os.path.exists(log_file):
                    print(f"最后100行日志:")
                    with open(log_file, "r") as f:
                        lines = f.readlines()
                        for line in lines[-100:]:
                            print(line.strip())
                
                break
            
            # 获取并显示进度
            progress = get_progress(project_id)
            print(json.dumps(progress, indent=2, ensure_ascii=False))
            
            # 检查是否所有任务都已完成
            if progress["completed_tasks"] == progress["total_tasks"] and progress["total_tasks"] > 0:
                print(f"项目 {project_id} 的所有任务已完成")
                break
                
            time.sleep(interval)
    except KeyboardInterrupt:
        print("监控已停止")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python scheduler.py [start|stop|status] [project_id] [prompt] [model_id]")
        return
    
    command = sys.argv[1]
    
    if command == "start":
        if len(sys.argv) < 5:
            print("用法: python scheduler.py start [project_id] [prompt] [model_id]")
            return
        
        project_id = sys.argv[2]
        prompt = sys.argv[3]
        model_id = sys.argv[4]
        
        pid = start_worker(project_id, prompt, model_id)
        if pid:
            print(f"开始监控项目 {project_id} 的处理进度...")
            monitor_progress(project_id)
    
    elif command == "stop":
        if len(sys.argv) < 3:
            print("用法: python scheduler.py stop [project_id]")
            return
        
        project_id = sys.argv[2]
        stop_worker(project_id)
    
    elif command == "status":
        if len(sys.argv) < 3:
            print("用法: python scheduler.py status [project_id]")
            return
        
        project_id = sys.argv[2]
        pid = is_process_running(project_id)
        
        if pid:
            print(f"项目 {project_id} 的worker进程正在运行 (PID: {pid})")
            progress = get_progress(project_id)
            print(json.dumps(progress, indent=2, ensure_ascii=False))
        else:
            print(f"项目 {project_id} 的worker进程未运行")

if __name__ == "__main__":
    main() 