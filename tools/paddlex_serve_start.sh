#!/bin/bash
# ===========================================================================
#  启动 PaddleOCR-VL 识别服务（PaddleOCR_PDF_to_md.py 的验证引擎）
#
#  用法：
#    ./tools/paddlex_serve_start.sh            # 前台运行（终端可见日志，Ctrl+C 关闭）
#    nohup ./tools/paddlex_serve_start.sh > paddle_serve.log 2>&1 &   # 后台常驻
#
#  可用环境变量覆盖默认值：
#    CONDA_ROOT        Anaconda 安装根（默认 /opt/anaconda）
#    CONDA_ENV         conda 环境名（默认 BaiduPaddle）
#    PADDLE_PIPELINE   PaddleOCR-VL pipeline 配置 yaml（默认见下）
#    PADDLE_PORT       服务端口（默认 8203）
#
#  关闭：./tools/paddlex_serve_stop.sh [端口]
# ===========================================================================
set -e
cd "$(dirname "$0")"

CONDA_ROOT="${CONDA_ROOT:-/opt/anaconda}"
CONDA_ENV="${CONDA_ENV:-BaiduPaddle}"
PADDLE_PIPELINE="${PADDLE_PIPELINE:-/home/shui/myservice/OCR/PaddleOCR/my_PaddleOCR-VL-1.6.yaml}"
PADDLE_PORT="${PADDLE_PORT:-8203}"

# shellcheck disable=SC1091
source "$CONDA_ROOT/bin/activate" root
conda activate "$CONDA_ENV"

exec paddlex --serve --pipeline "$PADDLE_PIPELINE" --port "$PADDLE_PORT"
