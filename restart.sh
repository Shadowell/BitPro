#!/bin/bash

# ============================================
# BitPro 重启脚本
# 用法: ./restart.sh [--backend-only | --frontend-only | --force]
# ============================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# ===== 参数解析 =====
ARGS=""
COMPONENT=""
for arg in "$@"; do
    case $arg in
        --backend-only)  COMPONENT="后端" ; ARGS="$ARGS --backend-only" ;;
        --frontend-only) COMPONENT="前端" ; ARGS="$ARGS --frontend-only" ;;
        --force|-f)      ARGS="$ARGS --force" ;;
        -h|--help)
            echo "用法: ./restart.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --backend-only   只重启后端"
            echo "  --frontend-only  只重启前端"
            echo "  --force, -f      强制杀掉进程后重启"
            echo "  -h, --help       显示帮助"
            echo ""
            echo "示例:"
            echo "  ./restart.sh                  # 重启全部"
            echo "  ./restart.sh --backend-only   # 只重启后端（前端不受影响）"
            echo "  ./restart.sh --force          # 强制重启"
            exit 0
            ;;
        *)
            echo "未知参数: $arg"
            exit 1
            ;;
    esac
done

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║          BitPro 重启脚本                 ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

if [ -n "$COMPONENT" ]; then
    echo -e "${YELLOW}重启模式: 仅${COMPONENT}${NC}"
else
    echo -e "${YELLOW}重启模式: 全部服务${NC}"
fi
echo ""

# 先停止
"$SCRIPT_DIR/stop.sh" $ARGS

sleep 1

# 再启动
"$SCRIPT_DIR/start.sh" $ARGS
