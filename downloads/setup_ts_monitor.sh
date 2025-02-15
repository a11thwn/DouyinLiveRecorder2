#!/bin/bash

# 设置Python脚本的执行权限
chmod +x ts_monitor.py

# 创建新的crontab任务
(crontab -l 2>/dev/null; echo "*/5 * * * * cd $(pwd) && ./ts_monitor.py") | crontab -

echo "设置完成！ts_monitor.py 将每5分钟执行一次"
