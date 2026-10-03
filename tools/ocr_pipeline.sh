#!/usr/bin/env bash
# ===========================================================================
#  高考真题材料处理：PDF → Markdown 多引擎交叉验证
#
#  用法：
#    tools/ocr_pipeline.sh <源PDF> <处理目录>
#  例：
#    tools/ocr_pipeline.sh Docx/2026/2026_湖北.pdf 材料处理/2026/湖北
#
#  流程：
#    [甲·底本] OvisOCR2        -> <处理目录>/ovis/output.md   + ovis/images/
#    [乙·验证] PaddleOCR-VL    -> <处理目录>/paddle/output.md + paddle/images/
#    [旁证]    pdftotext       -> <处理目录>/pdftotext.txt
#    然后 tools/material_merge.py 生成 merged.md，
#    再用 tools/pdf_extract_images.py 从原 PDF 无损提取内嵌图到 pdfimages/。
#
#  依赖环境（与本机一致）：
#    * OvisOCR2：Anaconda 环境 ovis_ocr，模型由 OVIS_MODEL 指定（示例 ~/AI/ATH-MaaS/OvisOCR2）
#    * PaddleOCR-VL：Anaconda 环境 BaiduPaddle，服务 127.0.0.1:8203
#        （先 tools/paddlex_serve_start.sh 启动，用完 tools/paddlex_serve_stop.sh 关闭）
#    * poppler：pdftotext / pdfimages
#  若 OvisOCR2 / PaddleOCR-VL 有其它安装方式，请修改下方对应命令。
# ===========================================================================
set -euo pipefail

PDF="${1:?用法: tools/ocr_pipeline.sh <源PDF> <处理目录>}"
OUT="${2:?用法: tools/ocr_pipeline.sh <源PDF> <处理目录>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

# conda 环境（可用环境变量覆盖）
CONDA_ROOT="${CONDA_ROOT:-/opt/anaconda}"
OVIS_ENV="${OVIS_ENV:-ovis_ocr}"
PADDLE_ENV="${PADDLE_ENV:-BaiduPaddle}"
OVIS_MODEL="${OVIS_MODEL:-$HOME/AI/ATH-MaaS/OvisOCR2}"

# 使 conda 命令可用（非交互 shell 默认无 conda）
if ! command -v conda >/dev/null 2>&1; then
    # shellcheck disable=SC1091
    source "$CONDA_ROOT/bin/activate" root
fi

mkdir -p "$OUT"

echo "== [旁证] pdftotext =="
pdftotext -layout "$PDF" "$OUT/pdftotext.txt" || echo "  （扫描版可忽略 pdftotext 失败）"

echo "== [乙·验证] PaddleOCR-VL （需先启动服务：tools/paddlex_serve_start.sh） =="
conda run -n "$PADDLE_ENV" python "$HERE/PaddleOCR_PDF_to_md.py" -i "$PDF" -o "$OUT/paddle"

echo "== [甲·底本] OvisOCR2 =="
conda run -n "$OVIS_ENV" python "$HERE/pdf_to_md.py" \
    --input "$PDF" \
    --output "$OUT/ovis" \
    --model-path "$OVIS_MODEL" \
    --enforce-eager

echo "== 生成 merged.md =="
python3 "$HERE/material_merge.py" "$OUT" --force

echo "== 无损提取内嵌图片 =="
python3 "$HERE/pdf_extract_images.py" "$OUT" --force

echo "完成：$OUT"
