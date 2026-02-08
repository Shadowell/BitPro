#!/bin/bash

# BitPro 启动脚本

echo "🚀 Starting BitPro..."

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 创建日志目录
mkdir -p "$SCRIPT_DIR/logs"

# 启动后端
echo -e "${YELLOW}Starting backend...${NC}"
cd "$SCRIPT_DIR/backend"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 启动后端服务
uvicorn app.main:app --host 0.0.0.0 --port 8889 > "$SCRIPT_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$SCRIPT_DIR/logs/backend.pid"
echo -e "${GREEN}Backend started (PID: $BACKEND_PID)${NC}"

# 等待后端启动
sleep 3

# 启动前端
echo -e "${YELLOW}Starting frontend...${NC}"
cd "$SCRIPT_DIR/frontend"

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# 启动前端服务
npm run dev > "$SCRIPT_DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$SCRIPT_DIR/logs/frontend.pid"
echo -e "${GREEN}Frontend started (PID: $FRONTEND_PID)${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}BitPro is running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Frontend: http://localhost:8888"
echo "Backend:  http://localhost:8889"
echo "API Docs: http://localhost:8889/docs"
echo ""
echo "To stop: ./stop.sh"
