#!/usr/bin/env python3
"""
文件名: ts_monitor.py
功能: 递归扫描当前目录及其子目录下的.ts文件，对每个目录中的ts文件进行处理：
      1. 当某个目录中的ts文件数量超过1个时，保留最新的文件，其余文件移动到云端
      2. 当目录中只有1个ts文件时，如果文件大小与上次扫描相同，则将其移动到云端
作者: Cascade AI
创建时间: 2025-02-14
更新时间: 2025-02-15
"""

import os
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ts_monitor.log'),
        logging.StreamHandler()
    ]
)

# 缓存文件路径
CACHE_FILE = Path('ts_monitor_cache.json')

def load_file_cache():
    """
    加载文件大小缓存
    返回: 包含文件大小信息的字典
    """
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logging.warning("缓存文件损坏，创建新的缓存")
    return {}

def save_file_cache(cache):
    """
    保存文件大小缓存
    参数:
        cache: 包含文件大小信息的字典
    """
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=4)

def get_ts_files(directory):
    """
    获取指定目录下所有的.ts文件
    参数:
        directory: 要扫描的目录路径
    返回: 按修改时间排序的.ts文件列表
    """
    # 使用Path对象获取目录下所有.ts文件
    ts_files = list(Path(directory).glob("*.ts"))
    # 按修改时间排序，最新的在前面
    ts_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return ts_files

def move_file_to_cloud(file_path):
    """
    使用rclone将文件移动到云端
    参数:
        file_path: 需要移动的文件路径
    """
    try:
        # 构造云端目标路径，保持目录结构
        relative_path = os.path.relpath(str(file_path), str(Path.cwd()))
        target_path = f"od-chan:youtube-dl/{os.path.dirname(relative_path)}"
        
        # 创建目标目录（如果不存在）
        mkdir_cmd = f"rclone mkdir {target_path}"
        subprocess.run(mkdir_cmd, shell=True, check=True)
        
        # 移动文件
        move_cmd = f"rclone move {file_path} {target_path}"
        subprocess.run(move_cmd, shell=True, check=True)
        logging.info(f"成功移动文件 {file_path} 到 {target_path}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"移动文件 {file_path} 失败: {str(e)}")
        return False

def process_directory(directory, file_cache):
    """
    处理指定目录中的.ts文件
    参数:
        directory: 要处理的目录路径
        file_cache: 文件大小缓存字典
    """
    # 获取当前目录下的.ts文件
    ts_files = get_ts_files(directory)
    
    if not ts_files:
        return
    
    if len(ts_files) > 1:
        logging.info(f"目录 {directory} 中发现{len(ts_files)}个.ts文件，开始处理")
        
        # 保留最新的文件，移动其他文件
        for file in ts_files[1:]:
            if move_file_to_cloud(file):
                file_cache.pop(str(file), None)  # 从缓存中移除已移动的文件
    else:
        # 只有一个文件的情况
        file = ts_files[0]
        current_size = file.stat().st_size
        file_path_str = str(file)
        
        if file_path_str in file_cache:
            # 如果文件在缓存中且大小没有变化
            if current_size == file_cache[file_path_str]:
                logging.info(f"文件 {file} 大小未变化，准备移动到云端")
                if move_file_to_cloud(file):
                    file_cache.pop(file_path_str)  # 从缓存中移除已移动的文件
            else:
                logging.info(f"文件 {file} 大小已改变，更新缓存")
                file_cache[file_path_str] = current_size
        else:
            # 新文件，添加到缓存
            logging.info(f"新文件 {file}，添加到缓存")
            file_cache[file_path_str] = current_size

def main():
    """
    主函数：递归扫描并处理所有目录中的.ts文件
    """
    logging.info("开始扫描目录")
    
    # 加载文件缓存
    file_cache = load_file_cache()
    
    # 获取当前目录
    current_dir = Path.cwd()
    
    # 递归遍历所有子目录
    for directory in [current_dir] + [d for d in current_dir.rglob("*") if d.is_dir()]:
        logging.info(f"正在检查目录: {directory}")
        process_directory(directory, file_cache)
    
    # 保存更新后的缓存
    save_file_cache(file_cache)
    logging.info("扫描完成")

if __name__ == "__main__":
    main()
