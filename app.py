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
from functools import wraps
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
import re

# 加载.env文件
load_dotenv()

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
            logger.error(f"Error reading URL config file: {e}")
            return {'content': ''}

    # 主配置文件使用INI格式处理
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str  # 保持键名的大小写
    try:
        # 先尝试直接读取
        config.read(config_file, encoding='utf-8')
    except configparser.MissingSectionHeaderError:
        # 如果失败，尝试处理BOM头
        with open(config_file, 'r', encoding='utf-8-sig') as f:
            config.read_file(f)
    except Exception as e:
        logger.error(f"Error reading config file {config_file}: {e}")
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
    try:
        # 确保配置目录存在
        config_dir = config_file.parent
        config_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensuring config directory exists: {config_dir}")
        
        # 如果是URL配置文件，直接保存文本内容
        if config_file == URL_CONFIG:
            try:
                content = config_data.get('content', '')
                if not isinstance(content, str):
                    content = ''  # 如果内容不是字符串类型，设置为空字符串
                    
                logger.info(f"Saving URL config to: {config_file}")
                with open(config_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info("URL config saved successfully")
                return
                
            except Exception as e:
                error_msg = f"Error saving URL config file: {str(e)}"
                logger.error(error_msg, exc_info=True)
                raise ValueError(error_msg)

        # 主配置文件使用INI格式保存
        config = configparser.ConfigParser(interpolation=None)
        config.optionxform = str  # 保持键名的大小写
        
        # 添加所有配置节
        for section, values in config_data.items():
            if not config.has_section(section):
                config.add_section(section)
            for key, value in values.items():
                config.set(section, key, str(value))
        
        # 保存到文件
        logger.info(f"Saving main config to: {config_file}")
        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)
        logger.info("Main config saved successfully")
        
    except Exception as e:
        error_msg = f"Error saving config file {config_file}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise ValueError(error_msg)

# 获取访问密码
ACCESS_PASSWORD = os.getenv('ACCESS_PASSWORD')
if not ACCESS_PASSWORD:
    logger.error("ACCESS_PASSWORD not set in .env file")
    sys.exit(1)

def login_required(f):
    """
    验证登录状态的装饰器
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ACCESS_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='密码错误')
    return render_template('login.html')

@app.route('/logout')
def logout():
    """登出"""
    session.pop('authenticated', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """主页路由"""
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
@login_required
def get_config():
    """获取配置内容"""
    main_config = read_config(MAIN_CONFIG)
    url_config = read_config(URL_CONFIG)
    return jsonify({
        'main_config': main_config,
        'url_config': url_config
    })

@app.route('/api/config', methods=['POST'])
@login_required
def update_config():
    """更新配置内容"""
    try:
        data = request.get_json()
        if data is None:
            raise ValueError("No JSON data received")
            
        logger.info("Received config update request")
        
        if 'main_config' in data:
            logger.info("Updating main config")
            save_config(MAIN_CONFIG, data['main_config'])
            socketio.emit('log', {'data': '主配置已更新'})
            
        if 'url_config' in data:
            logger.info("Updating URL config")
            save_config(URL_CONFIG, data['url_config'])
            socketio.emit('log', {'data': 'URL配置已更新'})
            
        return jsonify({'status': 'success'})
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Config update failed: {error_msg}", exc_info=True)
        return jsonify({'status': 'error', 'message': error_msg}), 400

@app.route('/api/control/<action>', methods=['POST'])
@login_required
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
@login_required
def get_status():
    """获取录制程序状态"""
    return jsonify({
        'is_running': is_running
    })

@socketio.on('connect')
def handle_connect():
    """处理WebSocket连接"""
    if not session.get('authenticated'):
        return False
    emit('status', {'is_running': is_running})

def clean_ansi_escape_sequences(text):
    """
    清理文本中的ANSI转义序列
    Args:
        text: 原始文本
    Returns:
        清理后的文本
    """
    # 匹配所有ANSI转义序列
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

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
                # 清理ANSI转义序列
                cleaned_line = clean_ansi_escape_sequences(line.strip())
                if cleaned_line:  # 确保不是空行
                    logger.info(f"Process output: {cleaned_line}")
                    # 使用 emit 发送日志到前端
                    socketio.emit('log', {'data': cleaned_line})
            
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
    global recorder_process, log_monitor_thread, is_running
    try:
        if recorder_process and recorder_process.poll() is None:
            return {'status': 'error', 'message': '程序已经在运行中'}

        # 获取当前工作目录
        cwd = os.path.dirname(os.path.abspath(__file__))
        main_py = os.path.join(cwd, 'main.py')
        if not os.path.exists(main_py):
            return {'status': 'error', 'message': '找不到 main.py 文件'}

        # 使用虚拟环境的Python解释器
        venv_python = os.path.join(cwd, 'venv', 'bin', 'python')
        if not os.path.exists(venv_python):
            return {'status': 'error', 'message': '找不到虚拟环境Python解释器'}

        # 设置环境变量
        env = os.environ.copy()
        env['PYTHONPATH'] = cwd  # 添加当前目录到Python路径
        env['VIRTUAL_ENV'] = os.path.join(cwd, 'venv')
        env['PATH'] = f"{os.path.join(env['VIRTUAL_ENV'], 'bin')}:{env.get('PATH', '')}"

        # 启动进程
        cmd = [venv_python, '-u', main_py]  # 添加 -u 参数禁用输出缓冲
        logger.info(f'Starting recorder with command: {cmd}')
        logger.info(f'Working directory: {cwd}')
        logger.info(f'Environment: PYTHONPATH={env.get("PYTHONPATH")}, PATH={env.get("PATH")}')
        
        recorder_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
            universal_newlines=True,
            bufsize=1
        )

        logger.info(f"Process started with PID: {recorder_process.pid}")
        is_running = True

        # 启动日志监控线程
        log_monitor_thread = threading.Thread(target=monitor_output, args=(recorder_process,))
        log_monitor_thread.daemon = True
        log_monitor_thread.start()

        return {'status': 'success', 'message': '程序已启动'}
    except Exception as e:
        error_msg = f'启动程序时发生错误: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {'status': 'error', 'message': error_msg}

def setup_virtual_environment():
    """
    设置虚拟环境并安装依赖
    Returns:
        bool: 是否成功设置虚拟环境
    """
    try:
        cwd = os.path.dirname(os.path.abspath(__file__))
        venv_path = os.path.join(cwd, 'venv')
        
        # 检查虚拟环境是否已存在
        if not os.path.exists(venv_path):
            logger.info("Creating virtual environment...")
            import venv
            venv.create(venv_path, with_pip=True)
            logger.info("Virtual environment created successfully")
        
        # 获取虚拟环境的Python和pip路径
        if sys.platform == 'win32':
            venv_python = os.path.join(venv_path, 'Scripts', 'python.exe')
            venv_pip = os.path.join(venv_path, 'Scripts', 'pip.exe')
        else:
            venv_python = os.path.join(venv_path, 'bin', 'python')
            venv_pip = os.path.join(venv_path, 'bin', 'pip')
        
        # 检查requirements.txt是否存在
        requirements_file = os.path.join(cwd, 'requirements.txt')
        if not os.path.exists(requirements_file):
            logger.error("requirements.txt not found")
            return False
        
        # 安装依赖
        logger.info("Installing dependencies...")
        subprocess.run([venv_pip, 'install', '-r', requirements_file], check=True)
        logger.info("Dependencies installed successfully")
        
        return True
    except Exception as e:
        logger.error(f"Error setting up virtual environment: {str(e)}", exc_info=True)
        return False

if __name__ == '__main__':
    logger.info("Starting Flask application")
    
    # 设置虚拟环境
    if not setup_virtual_environment():
        logger.error("Failed to setup virtual environment. Exiting...")
        sys.exit(1)
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5678) 