# -*- encoding: utf-8 -*-

"""
Author: AI Assistant
Date: 2024-02-08
Update: 2024-02-08
Function: Web interface for managing DouyinLiveRecorder configuration and control
This module provides a web interface to:
1. View and modify configuration files
2. Control the recorder (start/stop)
3. View real-time console output
"""

import os
import sys
import configparser
import subprocess
import threading
import logging
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

# 配置日志
logging.basicConfig(level=logging.DEBUG,
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 初始化Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 配置文件路径
CONFIG_DIR = Path('config')
MAIN_CONFIG = CONFIG_DIR / 'config.ini'
URL_CONFIG = CONFIG_DIR / 'URL_config.ini'

# 全局变量
recorder_process = None
is_running = False
log_monitor_thread = None

def read_config(config_file):
    """
    读取配置文件
    Args:
        config_file: 配置文件路径
    Returns:
        配置内容的字典
    """
    if not config_file.exists():
        return {}

    # 如果是URL配置文件，直接读取文本内容
    if config_file == URL_CONFIG:
        try:
            with open(config_file, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            return {'content': content}
        except Exception as e:
            print(f"Error reading URL config file: {e}")
            return {'content': ''}

    # 主配置文件使用INI格式处理
    config = configparser.ConfigParser(interpolation=None)
    try:
        # 先尝试直接读取
        config.read(config_file, encoding='utf-8')
    except configparser.MissingSectionHeaderError:
        # 如果失败，尝试处理BOM头
        with open(config_file, 'r', encoding='utf-8-sig') as f:
            config.read_file(f)
    except Exception as e:
        print(f"Error reading config file {config_file}: {e}")
        return {}

    result = {}
    for section in config.sections():
        result[section] = {}
        for key, value in config.items(section):
            result[section][key] = value
    return result

def save_config(config_file, config_data):
    """
    保存配置文件
    Args:
        config_file: 配置文件路径
        config_data: 配置内容的字典
    """
    # 如果是URL配置文件，直接保存文本内容
    if config_file == URL_CONFIG:
        try:
            content = config_data.get('content', '')
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return
        except Exception as e:
            print(f"Error saving URL config file: {e}")
            raise

    # 主配置文件使用INI格式保存
    try:
        config = configparser.ConfigParser(interpolation=None)
        config.optionxform = str  # 保持键名的大小写
        
        # 添加所有配置节
        for section, values in config_data.items():
            if not config.has_section(section):
                config.add_section(section)
            for key, value in values.items():
                config.set(section, key, str(value))
        
        # 保存到文件
        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)
    except Exception as e:
        print(f"Error saving config file {config_file}: {e}")
        raise

@app.route('/')
def index():
    """主页路由"""
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取配置内容"""
    main_config = read_config(MAIN_CONFIG)
    url_config = read_config(URL_CONFIG)
    return jsonify({
        'main_config': main_config,
        'url_config': url_config
    })

@app.route('/api/config', methods=['POST'])
def update_config():
    """更新配置内容"""
    try:
        data = request.get_json()
        if 'main_config' in data:
            save_config(MAIN_CONFIG, data['main_config'])
        if 'url_config' in data:
            save_config(URL_CONFIG, data['url_config'])
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/api/control/<action>', methods=['POST'])
def control_recorder(action):
    """
    控制录制程序
    Args:
        action: start 或 stop
    """
    global recorder_process, is_running, log_monitor_thread

    logger.info(f"Received control action: {action}")

    if action == 'start' and not is_running:
        try:
            # 检查main.py是否存在
            cwd = os.path.dirname(os.path.abspath(__file__))
            main_py = os.path.join(cwd, 'main.py')
            if not os.path.exists(main_py):
                raise FileNotFoundError("main.py not found")

            # 使用虚拟环境的Python解释器
            venv_python = os.path.join(cwd, 'venv', 'bin', 'python')
            if not os.path.exists(venv_python):
                raise FileNotFoundError("Virtual environment Python interpreter not found")
            
            logger.info(f"Using Python interpreter: {venv_python}")
            logger.info(f"Current working directory: {cwd}")

            # 设置环境变量
            env = os.environ.copy()
            env['PYTHONPATH'] = cwd  # 添加当前目录到Python路径
            if 'VIRTUAL_ENV' in env:
                env['PATH'] = f"{os.path.join(env['VIRTUAL_ENV'], 'bin')}:{env['PATH']}"
            
            # 启动录制程序，确保不使用缓冲
            cmd = [venv_python, '-u', main_py]  # 添加 -u 参数禁用输出缓冲
            logger.info(f"Starting process with command: {cmd}")
            
            recorder_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,  # Line buffering
                env=env,
                cwd=cwd
            )
            
            logger.info(f"Process started with PID: {recorder_process.pid}")
            is_running = True
            
            # 启动日志监控线程
            log_monitor_thread = threading.Thread(target=monitor_output, args=(recorder_process,))
            log_monitor_thread.daemon = True
            log_monitor_thread.start()
            
            # 发送初始状态
            socketio.emit('status', {'is_running': True})
            socketio.emit('log', {'data': f'程序已启动 (PID: {recorder_process.pid})'})
            
            return jsonify({'status': 'success', 'message': '程序已启动'})
            
        except Exception as e:
            error_msg = f"Error starting process: {str(e)}"
            logger.error(error_msg, exc_info=True)
            socketio.emit('log', {'data': f"错误: {error_msg}"})
            return jsonify({'status': 'error', 'message': f'启动失败: {str(e)}'}), 500

    elif action == 'stop' and is_running:
        try:
            logger.info("Stopping recorder process")
            recorder_process.terminate()
            recorder_process.wait(timeout=5)
            is_running = False
            logger.info("Recorder process stopped")
            return jsonify({'status': 'success', 'message': '录制程序已停止'})
        except Exception as e:
            logger.error(f"Error stopping process: {str(e)}", exc_info=True)
            return jsonify({'status': 'error', 'message': f'停止失败: {str(e)}'}), 500

    return jsonify({'status': 'error', 'message': '无效的操作'}), 400

@app.route('/api/status')
def get_status():
    """获取录制程序状态"""
    return jsonify({
        'is_running': is_running
    })

@socketio.on('connect')
def handle_connect():
    """处理WebSocket连接"""
    emit('status', {'is_running': is_running})

def monitor_output(process):
    """
    监控进程输出的线程函数
    Args:
        process: 要监控的进程
    """
    global is_running
    logger.info("Starting output monitor")
    
    try:
        # 发送初始状态
        socketio.emit('status', {'is_running': True})
        socketio.emit('log', {'data': '程序启动中...'})
        
        # 使用迭代器读取输出，这样可以实时获取输出
        for line in iter(process.stdout.readline, ''):
            if line:
                line = line.strip()
                if line:  # 确保不是空行
                    logger.info(f"Process output: {line}")
                    # 使用 emit 发送日志到前端
                    socketio.emit('log', {'data': line})
            
            # 检查进程是否已经结束
            if process.poll() is not None:
                logger.info("Process ended")
                break
                
    except Exception as e:
        error_msg = f"Error monitoring output: {str(e)}"
        logger.error(error_msg, exc_info=True)
        socketio.emit('log', {'data': f"错误: {error_msg}"})
    finally:
        # 进程结束，更新状态
        is_running = False
        logger.info("Process status updated to stopped")
        socketio.emit('status', {'is_running': False})
        socketio.emit('log', {'data': '程序已停止'})
        
        # 确保关闭所有管道
        try:
            process.stdout.close()
        except:
            pass

def start_recorder():
    global recorder_process, log_monitor_thread
    try:
        if recorder_process and recorder_process.poll() is None:
            return {'status': 'error', 'message': '程序已经在运行中'}

        # 获取当前工作目录
        cwd = os.path.dirname(os.path.abspath(__file__))
        main_py = os.path.join(cwd, 'main.py')
        if not os.path.exists(main_py):
            return {'status': 'error', 'message': '找不到 main.py 文件'}

        # 使用系统 Python3 解释器
        python_paths = ['/usr/local/bin/python3', '/usr/bin/python3', 'python3']
        python_path = None
        for path in python_paths:
            if os.path.exists(path) or os.system(f'which {path} > /dev/null 2>&1') == 0:
                python_path = path
                break
        
        if not python_path:
            return {'status': 'error', 'message': '找不到 Python3 解释器'}

        # 设置环境变量
        env = os.environ.copy()
        env['PYTHONPATH'] = cwd  # 添加当前目录到 Python 路径
        if 'VIRTUAL_ENV' in env:
            env['PATH'] = f"{os.path.join(env['VIRTUAL_ENV'], 'bin')}:{env['PATH']}"

        # 启动进程
        cmd = [python_path, main_py]
        logging.info(f'Starting recorder with command: {cmd}')
        logging.info(f'Working directory: {cwd}')
        logging.info(f'Environment: PYTHONPATH={env.get("PYTHONPATH")}, PATH={env.get("PATH")}')
        
        recorder_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
            universal_newlines=True,
            bufsize=1
        )

        # 启动日志监控线程
        log_monitor_thread = threading.Thread(target=monitor_output, args=(recorder_process,))
        log_monitor_thread.daemon = True
        log_monitor_thread.start()

        return {'status': 'success', 'message': '程序已启动'}
    except Exception as e:
        logging.error(f'启动程序时发生错误: {str(e)}')
        return {'status': 'error', 'message': f'启动程序时发生错误: {str(e)}'}

if __name__ == '__main__':
    logger.info("Starting Flask application")
    socketio.run(app, debug=True, host='0.0.0.0', port=5678) 