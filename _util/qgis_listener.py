#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QGIS 命令监听器
用于从Terminal触发QGIS脚本执行，不会干扰当前打开的项目

使用方法：
1. 在QGIS中打开你的项目
2. 在Python Console中运行：
   exec(open(str(Path.home() / 'Dev/scripts/projects/qgis/_util/qgis_listener.py')).read())
3. 监听器开始工作（后台运行）
4. 在Terminal中使用 qgis-run 命令执行脚本
"""

import os
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime
from qgis.core import QgsProject, QgsMessageLog, Qgis
from qgis.PyQt.QtCore import QTimer

# ==================== 配置 ====================

# 脚本目录
SCRIPT_DIR = Path(__file__).resolve().parent.parent / 'pipeline' if '__file__' in dir() else Path.home() / 'Dev/scripts/projects/qgis/pipeline'

# 通信文件
COMMAND_FILE = Path.home() / ".qgis_command.txt"
RESULT_FILE = Path.home() / ".qgis_result.txt"
LOCK_FILE = Path.home() / ".qgis_lock.txt"

# 检查间隔（毫秒）
CHECK_INTERVAL = 500  # 0.5秒检查一次

# ==================== 监听器类 ====================

class QGISCommandListener:
    """QGIS命令监听器"""
    
    def __init__(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_command)
        self.is_running = False
        self.last_check_time = None
        
        # 清理旧的通信文件
        self._cleanup_files()
        
        print("=" * 80)
        print("🎧 QGIS 命令监听器已初始化")
        print("=" * 80)
        print(f"📁 脚本目录: {SCRIPT_DIR}")
        print(f"📝 命令文件: {COMMAND_FILE}")
        print(f"📊 结果文件: {RESULT_FILE}")
        print(f"⏱️  检查间隔: {CHECK_INTERVAL}ms")
        print("=" * 80)
    
    def _cleanup_files(self):
        """清理旧的通信文件"""
        for f in [COMMAND_FILE, RESULT_FILE, LOCK_FILE]:
            if f.exists():
                f.unlink()
    
    def _log(self, message, level=Qgis.Info):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        QgsMessageLog.logMessage(message, "QGIS Listener", level)
    
    def start(self):
        """启动监听"""
        if self.is_running:
            self._log("⚠️  监听器已在运行中", Qgis.Warning)
            return
        
        self.is_running = True
        self.timer.start(CHECK_INTERVAL)
        self._log("✅ 监听器已启动！等待Terminal命令...")
        self._log(f"💡 使用方法: qgis-run <脚本名称>")
    
    def stop(self):
        """停止监听"""
        if not self.is_running:
            return
        
        self.is_running = False
        self.timer.stop()
        self._cleanup_files()
        self._log("🛑 监听器已停止")
    
    def check_command(self):
        """检查是否有新命令"""
        self.last_check_time = datetime.now()
        
        # 检查锁文件（防止并发）
        if LOCK_FILE.exists():
            return
        
        # 检查命令文件
        if not COMMAND_FILE.exists():
            return
        
        # 读取命令
        try:
            with open(COMMAND_FILE, 'r', encoding='utf-8') as f:
                command_data = f.read().strip()
            
            if not command_data:
                return
            
            # 解析命令（格式：SCRIPT_NAME）
            script_name = command_data.strip()
            
            # 删除命令文件（避免重复执行）
            COMMAND_FILE.unlink()
            
            # 创建锁文件
            LOCK_FILE.write_text("locked")
            
            # 执行命令
            self._log("=" * 80)
            self._log(f"📥 收到命令: {script_name}")
            self._execute_script(script_name)
            
        except Exception as e:
            error_msg = f"❌ 命令处理失败: {str(e)}\n{traceback.format_exc()}"
            self._log(error_msg, Qgis.Critical)
            self._write_result("ERROR", error_msg)
        finally:
            # 释放锁
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
    
    def _execute_script(self, script_name):
        """执行指定的Python脚本"""
        script_path = SCRIPT_DIR / script_name
        
        # 检查脚本是否存在
        if not script_path.exists():
            error_msg = f"❌ 脚本不存在: {script_path}"
            self._log(error_msg, Qgis.Critical)
            self._write_result("ERROR", error_msg)
            return
        
        self._log(f"🚀 开始执行: {script_path.name}")
        self._log(f"📂 当前项目: {QgsProject.instance().fileName() or '未保存的项目'}")
        
        start_time = time.time()
        
        # 将脚本目录添加到sys.path（以便导入同目录下的模块）
        script_dir = str(script_path.parent)
        sys_path_modified = False
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
            sys_path_modified = True
        
        try:
            # 读取脚本内容
            script_content = script_path.read_text(encoding='utf-8')
            
            # 在当前环境中执行
            exec_globals = {
                '__file__': str(script_path),
                '__name__': '__main__',
            }
            
            # 捕获输出
            from io import StringIO
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = StringIO()
            sys.stderr = StringIO()
            
            try:
                exec(compile(script_content, str(script_path), 'exec'), exec_globals)
                stdout_output = sys.stdout.getvalue()
                stderr_output = sys.stderr.getvalue()
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
            # 计算执行时间
            duration = time.time() - start_time
            
            # 构建结果
            result_msg = f"""
✅ 脚本执行成功！

脚本: {script_name}
耗时: {duration:.2f}秒
项目: {QgsProject.instance().fileName() or '未保存的项目'}

标准输出:
{stdout_output if stdout_output else '(无输出)'}

标准错误:
{stderr_output if stderr_output else '(无错误)'}
""".strip()
            
            self._log(f"✅ 执行成功！耗时 {duration:.2f}秒")
            self._write_result("SUCCESS", result_msg)
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"""
❌ 脚本执行失败！

脚本: {script_name}
耗时: {duration:.2f}秒
错误类型: {type(e).__name__}
错误信息: {str(e)}

详细追踪:
{traceback.format_exc()}
""".strip()
            
            self._log(f"❌ 执行失败: {str(e)}", Qgis.Critical)
            self._write_result("ERROR", error_msg)
        finally:
            # 清理sys.path（如果之前添加过）
            if sys_path_modified and script_dir in sys.path:
                sys.path.remove(script_dir)
    
    def _write_result(self, status, message):
        """写入执行结果"""
        try:
            result_content = f"{status}\n{'-' * 80}\n{message}\n"
            RESULT_FILE.write_text(result_content, encoding='utf-8')
            self._log(f"📤 结果已写入: {RESULT_FILE}")
        except Exception as e:
            self._log(f"❌ 写入结果失败: {str(e)}", Qgis.Critical)
    
    def status(self):
        """显示监听器状态"""
        print("\n" + "=" * 80)
        print("📊 QGIS命令监听器状态")
        print("=" * 80)
        print(f"运行状态: {'🟢 运行中' if self.is_running else '🔴 已停止'}")
        print(f"检查间隔: {CHECK_INTERVAL}ms")
        print(f"上次检查: {self.last_check_time.strftime('%H:%M:%S') if self.last_check_time else '未开始'}")
        print(f"命令文件: {COMMAND_FILE} {'✅' if COMMAND_FILE.exists() else '❌'}")
        print(f"结果文件: {RESULT_FILE} {'✅' if RESULT_FILE.exists() else '❌'}")
        print(f"锁文件:   {LOCK_FILE} {'🔒' if LOCK_FILE.exists() else '🔓'}")
        print("=" * 80)
        print("\n💡 使用方法:")
        print("   listener.start()   # 启动监听")
        print("   listener.stop()    # 停止监听")
        print("   listener.status()  # 查看状态")
        print("\n💡 Terminal命令:")
        print(f"   qgis-run 01_generate_river_points.py")
        print("=" * 80 + "\n")

# ==================== 全局实例 ====================

# 创建全局监听器实例
if 'listener' not in globals():
    listener = QGISCommandListener()

# 自动启动
listener.start()

print("\n" + "=" * 80)
print("🎉 监听器已启动！现在可以从Terminal运行命令了")
print("=" * 80)
print("\n💡 快速命令:")
print("   listener.status()  # 查看状态")
print("   listener.stop()    # 停止监听")
print("   listener.start()   # 重新启动")
print("\n💡 Terminal使用:")
print("   qgis-run 01_generate_river_points.py")
print("=" * 80 + "\n")

