#!/usr/bin/env bash
# ===========================================================================
#  tools/ocr_pipeline_all.sh —— 全库材料处理“一键编排”（无人值守）
#
#  按 `材料处理与OCR规范.md` 依次跑完五个阶段，任一阶段失败即停并返回非零；
#  各阶段内部由 tools/ocr_batch.py 断点续跑（已完成的产物自动跳过）。
#
#    [1] pdftotext  旁证           （CPU，快）
#    [2] PaddleOCR-VL 验证引擎      （自动启停服务 + 端口健康检查）
#    [3] OvisOCR2 底本             （vLLM 单进程复用模型）
#    [4] merged.md                 （三路交叉验证主数据源）
#    [5] pdfimages 无损提图
#
#  用法：
#    tools/ocr_pipeline_all.sh                 # 全库
#    tools/ocr_pipeline_all.sh --year 2026     # 透传 ocr_batch.py 的筛选参数
#    tools/ocr_pipeline_all.sh --force         # 已有产物也重跑
#    OCR_BATCH_LOG=/path/to/log tools/ocr_pipeline_all.sh
#
#  依赖：poppler（pdftotext/pdfimages）、conda 环境 ovis_ocr、PaddleOCR-VL
#       （服务端口默认 8203；若改端口需同时设 PADDLE_PORT 与 ocr_batch 客户端）。
# ===========================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

ARGS=("$@")
LOG="${OCR_BATCH_LOG:-/tmp/opencode/ocr_pipeline_all.log}"
SERVE_LOG="${OCR_SERVE_LOG:-/tmp/opencode/paddle_serve_all.log}"
PORT="${PADDLE_PORT:-8203}"
SERVE_PID=""

mkdir -p "$(dirname "$LOG")" "$(dirname "$SERVE_LOG")"
# 兼容 bash <4.4 的 set -u 空数组展开
PASSTHRU=(${ARGS[@]+"${ARGS[@]}"})
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

stop_serve() {
    "$HERE/paddlex_serve_stop.sh" "$PORT" >/dev/null 2>&1 || true
}
cleanup() { stop_serve; }
trap cleanup EXIT

wait_port() {
    local waited=0
    until (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; do
        waited=$((waited + 5))
        if [ "$waited" -ge 300 ]; then
            return 1
        fi
        sleep 5
    done
    return 0
}

log "===== 阶段 1/5：pdftotext（旁证）====="
python3 tools/ocr_batch.py pdftotext "${PASSTHRU[@]}"

log "===== 阶段 2/5：PaddleOCR-VL（验证引擎）====="
nohup "$HERE/paddlex_serve_start.sh" >"$SERVE_LOG" 2>&1 &
SERVE_PID=$!
if ! wait_port; then
    log "[错误] PaddleOCR-VL 服务在 300s 内未能监听端口 $PORT；详见 $SERVE_LOG"
    exit 1
fi
log "服务已就绪（端口 $PORT，pid $SERVE_PID）"
python3 tools/ocr_batch.py paddle "${PASSTHRU[@]}"
stop_serve
SERVE_PID=""
log "Paddle 阶段完成，服务已停止。"

log "===== 阶段 3/5：OvisOCR2（底本）====="
OVIS_PY="${OVIS_PYTHON:-/home/shui/.conda/envs/ovis_ocr/bin/python}"
"$OVIS_PY" tools/ocr_batch.py ovis "${PASSTHRU[@]}"

log "===== 阶段 4/5：生成 merged.md ====="
python3 tools/ocr_batch.py merge --force

log "===== 阶段 5/5：无损提取内嵌图 ====="
python3 tools/ocr_batch.py extract --force

log "===== 全部完成 ====="
