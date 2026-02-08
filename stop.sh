#!/bin/bash

# BitPro 停止脚本

echo "🛑 Stopping BitPro..."

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 停止后端
if [ -f "$SCRIPT_DIR/logs/backend.pid" ]; then
    BACKEND_PID=$(cat "$SCRIPT_DIR/logs/backend.pid")
    if ps -p $BACKEND_PID > /dev/null 2>&1; then
        kill $BACKEND_PID
        echo "Backend stopped (PID: $BACKEND_PID)"
    fi
    rm "$SCRIPT_DIR/logs/backend.pid"
fi

# 停止前端
if [ -f "$SCRIPT_DIR/logs/frontend.pid" ]; then
    FRONTEND_PID=$(cat "$SCRIPT_DIR/logs/frontend.pid")
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        kill $FRONTEND_PID
        echo "Frontend stopped (PID: $FRONTEND_PID)"
    fi
    rm "$SCRIPT_DIR/logs/frontend.pid"
fi

# 清理可能残留的进程
pkill -f "uvicorn app.main:app" 2>/dev/null
pkill -f "vite" 2>/dev/null

echo "BitPro stopped."
