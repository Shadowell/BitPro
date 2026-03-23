#!/bin/bash

# ============================================
# BitPro 一键部署/初始化脚本
# 用法: ./deploy.sh [--clean | --update | --check]
# 适用于首次部署或更新代码后重新初始化
# ============================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
LOG_DIR="$SCRIPT_DIR/logs"

MODE="deploy"  # deploy | clean | update | check

for arg in "$@"; do
    case $arg in
        --clean)  MODE="clean" ;;
        --update) MODE="update" ;;
        --check)  MODE="check" ;;
        -h|--help)
            echo "用法: ./deploy.sh [选项]"
            echo ""
            echo "选项:"
            echo "  (无)       首次部署/完整初始化"
            echo "  --update   更新依赖（保留数据和配置）"
            echo "  --clean    清理所有生成文件（venv/node_modules/logs/db）"
            echo "  --check    仅检查环境，不做任何修改"
            echo "  -h, --help 显示帮助"
            echo ""
            echo "首次使用流程:"
            echo "  1. ./deploy.sh         # 初始化环境"
            echo "  2. 编辑 backend/.env    # 填写 API Key"
            echo "  3. ./start.sh          # 启动服务"
            exit 0
            ;;
        *)
            echo -e "${RED}未知参数: $arg${NC}"
            exit 1
            ;;
    esac
done

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║          BitPro 部署脚本                 ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  模式: ${BOLD}$MODE${NC}"
echo -e "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ===== 清理模式 =====
if [ "$MODE" = "clean" ]; then
    echo -e "${YELLOW}⚠ 清理模式：将删除所有生成文件${NC}"
    echo ""
    read -p "确认清理? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "已取消"
        exit 0
    fi

    # 先停止服务
    if lsof -ti :8889 >/dev/null 2>&1 || lsof -ti :8888 >/dev/null 2>&1; then
        echo "停止运行中的服务..."
        "$SCRIPT_DIR/stop.sh" --force 2>/dev/null || true
    fi

    echo -n "清理后端虚拟环境..."
    rm -rf "$BACKEND_DIR/venv"
    echo -e " ${GREEN}✓${NC}"

    echo -n "清理前端 node_modules..."
    rm -rf "$FRONTEND_DIR/node_modules"
    echo -e " ${GREEN}✓${NC}"

    echo -n "清理日志文件..."
    rm -rf "$LOG_DIR"
    echo -e " ${GREEN}✓${NC}"

    echo -n "清理 Python 缓存..."
    find "$BACKEND_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$BACKEND_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
    echo -e " ${GREEN}✓${NC}"

    echo ""
    echo -e "${GREEN}✓ 清理完成${NC}"
    echo -e "  如需重新部署，请运行: ${CYAN}./deploy.sh${NC}"
    exit 0
fi

# ===== 环境检查 =====
echo -e "${BOLD}[1/5] 系统环境检查${NC}"

ERRORS=0

check_tool() {
    local cmd="$1"
    local min_ver="$2"
    local install_hint="$3"

    if ! command -v "$cmd" &> /dev/null; then
        echo -e "  ${RED}✗ $cmd 未安装${NC}"
        echo -e "    安装方式: ${YELLOW}$install_hint${NC}"
        ERRORS=$((ERRORS + 1))
        return 1
    fi

    local ver=$($cmd --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
    echo -e "  ${GREEN}✓${NC} $cmd (v$ver)"
    return 0
}

check_tool "python3" "3.11" "brew install python@3.11 / apt install python3.11"
check_tool "pip3" "23" "python3 -m ensurepip --upgrade" || check_tool "pip" "23" "python3 -m ensurepip --upgrade"
check_tool "node" "18" "brew install node / nvm install 18"
check_tool "npm" "9" "随 node 一起安装"
check_tool "curl" "7" "系统自带"

# 检查系统资源
echo ""
echo -e "  系统资源:"
TOTAL_MEM=$(sysctl -n hw.memsize 2>/dev/null || free -b 2>/dev/null | awk '/Mem:/ {print $2}')
if [ -n "$TOTAL_MEM" ]; then
    MEM_GB=$((TOTAL_MEM / 1024 / 1024 / 1024))
    echo -e "  ${GREEN}✓${NC} 内存: ${MEM_GB}GB"
fi
DISK_AVAIL=$(df -h "$SCRIPT_DIR" 2>/dev/null | tail -1 | awk '{print $4}')
echo -e "  ${GREEN}✓${NC} 磁盘可用: $DISK_AVAIL"

echo ""

if [ "$ERRORS" -gt 0 ]; then
    echo -e "${RED}✗ 发现 $ERRORS 个环境问题，请先修复后重新运行${NC}"
    exit 1
fi

if [ "$MODE" = "check" ]; then
    echo -e "${GREEN}✓ 环境检查通过，所有依赖已就绪${NC}"
    exit 0
fi

# ===== 后端部署 =====
echo -e "${BOLD}[2/5] 后端环境初始化${NC}"

cd "$BACKEND_DIR"

if [ "$MODE" = "update" ] && [ -d "venv" ]; then
    echo "  更新 Python 依赖..."
    source venv/bin/activate
    pip install -r requirements.txt -q --upgrade
    echo -e "  ${GREEN}✓ 依赖已更新${NC}"
else
    if [ ! -d "venv" ]; then
        echo "  创建 Python 虚拟环境..."
        python3 -m venv venv
    fi
    source venv/bin/activate
    echo "  安装 Python 依赖..."
    pip install -r requirements.txt -q
    echo -e "  ${GREEN}✓ 虚拟环境已就绪${NC}"
fi

# .env 配置文件
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "  ${YELLOW}⚠ 已创建 .env 配置文件（从 .env.example 复制）${NC}"
    echo -e "  ${YELLOW}  请编辑 backend/.env 填入交易所 API Key${NC}"
else
    echo -e "  ${GREEN}✓ .env 配置文件已存在${NC}"
fi
echo ""

# ===== 前端部署 =====
echo -e "${BOLD}[3/5] 前端环境初始化${NC}"

cd "$FRONTEND_DIR"

if [ "$MODE" = "update" ] && [ -d "node_modules" ]; then
    echo "  更新前端依赖..."
    npm install --silent
    echo -e "  ${GREEN}✓ 依赖已更新${NC}"
else
    echo "  安装前端依赖..."
    npm install --silent
    echo -e "  ${GREEN}✓ node_modules 已就绪${NC}"
fi
echo ""

# ===== 数据目录 =====
echo -e "${BOLD}[4/5] 数据目录初始化${NC}"

mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/data"
mkdir -p "$SCRIPT_DIR/docs"

echo -e "  ${GREEN}✓${NC} logs/   日志目录"
echo -e "  ${GREEN}✓${NC} data/   数据目录"
echo -e "  ${GREEN}✓${NC} docs/   文档目录"
echo ""

# ===== 脚本权限 =====
echo -e "${BOLD}[5/5] 设置脚本权限${NC}"

for script in start.sh stop.sh restart.sh status.sh deploy.sh; do
    if [ -f "$SCRIPT_DIR/$script" ]; then
        chmod +x "$SCRIPT_DIR/$script"
        echo -e "  ${GREEN}✓${NC} $script"
    fi
done
if [ -f "$SCRIPT_DIR/tests/run_tests.sh" ]; then
    chmod +x "$SCRIPT_DIR/tests/run_tests.sh"
    echo -e "  ${GREEN}✓${NC} tests/run_tests.sh"
fi
echo ""

# ===== 部署完成 =====
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          部署完成！                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}接下来的步骤:${NC}"
echo ""
if [ ! -f "$BACKEND_DIR/.env" ] || grep -q "your_okx_api_key" "$BACKEND_DIR/.env" 2>/dev/null; then
    echo -e "  1. ${YELLOW}编辑 API 配置:${NC}"
    echo -e "     ${CYAN}vim backend/.env${NC}"
    echo ""
    echo -e "  2. ${YELLOW}启动服务:${NC}"
    echo -e "     ${CYAN}./start.sh${NC}"
else
    echo -e "  1. ${YELLOW}启动服务:${NC}"
    echo -e "     ${CYAN}./start.sh${NC}"
fi
echo ""
echo -e "  ${BOLD}常用命令:${NC}"
echo -e "    ${CYAN}./start.sh${NC}     启动服务"
echo -e "    ${CYAN}./stop.sh${NC}      停止服务"
echo -e "    ${CYAN}./restart.sh${NC}   重启服务"
echo -e "    ${CYAN}./status.sh${NC}    查看状态"
echo ""
echo -e "    ${CYAN}./restart.sh --backend-only${NC}   只重启后端"
echo -e "    ${CYAN}./restart.sh --frontend-only${NC}  只重启前端"
echo -e "    ${CYAN}./deploy.sh --update${NC}          更新依赖"
echo -e "    ${CYAN}./deploy.sh --clean${NC}           清理环境"
echo ""
