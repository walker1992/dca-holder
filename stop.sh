#!/bin/bash

# 读取 PID 文件中的进程 ID
if [ -f "quantify.pid" ]; then
    PID=$(cat quantify.pid)

    # 检查该进程是否正在运行
    if ps -p $PID > /dev/null; then
        echo "正在停止进程：$PID"
        kill $PID
        rm -f quantify.pid
        echo "进程已终止"
    else
        echo "进程 $PID 不存在"
        rm -f quantify.pid
    fi
else
    echo "未找到 PID 文件，服务可能未运行"
fi