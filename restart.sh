#!/bin/bash

# BitPro 重启脚本

echo "🔄 Restarting BitPro..."

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 先停止
"$SCRIPT_DIR/stop.sh"

# 等待进程完全退出
sleep 2

# 再启动
"$SCRIPT_DIR/start.sh"
