#!/bin/bash

# 启动 Python 主程序，并后台运行
nohup python3 main.py > okx-quantify.log 2>&1 &

# 获取刚刚启动的后台进程的 PID
PID=$!

# 将 PID 写入文件，方便后续 stop.sh 使用
echo $PID > quantify.pid

# 输出提示信息
echo "服务已启动，PID: $PID"