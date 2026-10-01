#!/bin/bash
# 关闭 PaddleOCR-VL 识别服务（默认端口 8203），释放 GPU 显存
# 用法: ./paddlex_serve_stop.sh [端口]

PORT="${1:-8203}"
PIDS=""

# 优先按监听端口查找进程
if command -v lsof >/dev/null 2>&1; then
    PIDS=$(lsof -ti tcp:"$PORT" 2>/dev/null)
fi
if [ -z "$PIDS" ] && command -v fuser >/dev/null 2>&1; then
    PIDS=$(fuser "$PORT"/tcp 2>/dev/null)
fi

if [ -n "$PIDS" ]; then
    kill $PIDS 2>/dev/null
    sleep 1
    # 仍未退出则强制结束
    kill -9 $PIDS 2>/dev/null
    echo "已关闭 PaddleOCR-VL 服务（端口 $PORT，PID: $PIDS）"
elif pkill -f "paddlex --serve" 2>/dev/null; then
    echo "已关闭 PaddleOCR-VL 服务（按进程名匹配 paddlex --serve）"
else
    echo "未发现运行中的 PaddleOCR-VL 服务（端口 $PORT）"
fi
