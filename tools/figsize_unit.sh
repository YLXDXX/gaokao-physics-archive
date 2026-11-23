#!/usr/bin/env bash
# tools/figsize_unit.sh —— 单卷图片尺寸处理编排（生成候选→映射→回填→验证→编译）。
#
# 用法（在仓库根或任意目录均可）：
#   tools/figsize_unit.sh 试卷/2026/北京
#   tools/figsize_unit.sh 试卷/2026/北京 --force --skip-compile
#   tools/figsize_unit.sh 试卷/2026/北京 --log-dir /tmp/opencode/figsize_logs
#
# 步骤：JPG→PNG → ocrpipe layout/draft/extract（无候选时）→ figsize_automap
#       → figsize_plan --skip-unreferenced → figsize_merge_fallback（仍 missing 时）
#       → figsize_fix_refs → figsize_apply → figsize_check → 外部 check
#       → make student/teacher/check。
#
# 需要：ocrpipe（OCRPipeLine）、make、Python 依赖（Pillow/numpy/PyMuPDF）。
# 日志默认写入 /tmp/opencode/figsize_logs/。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO" || exit 2

U=""
FORCE=0
SKIP_COMPILE=0
LOG_DIR="/tmp/opencode/figsize_logs"
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    --skip-compile) SKIP_COMPILE=1 ;;
    --log-dir) shift; LOG_DIR="${1:-}" ;;
    -h|--help)
      sed -n '2,18p' "$0"; exit 0 ;;
    -*) echo "未知参数：$1" >&2; exit 2 ;;
    *) [ -z "$U" ] && U="$1" || { echo "只接受一个 UNIT" >&2; exit 2; } ;;
  esac
  shift
done
[ -n "$U" ] || { echo "用法：tools/figsize_unit.sh 试卷/<年>/<地区> [--force] [--skip-compile]" >&2; exit 2; }
U="${U%/}"
Y="$(echo "$U" | cut -d/ -f2)"; R="$(echo "$U" | cut -d/ -f3)"
[ -n "$Y" ] && [ -n "$R" ] || { echo "UNIT 形如 试卷/<年>/<地区>" >&2; exit 2; }
SAFE="${Y}_${R//\//_}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${SAFE}.log"
exec > >(tee "$LOG") 2>&1
echo "===== $(date '+%F %T') PROCESS $U ====="

# 0. 已完成则跳过（--force 可强制重做）
python3 tools/figsize_status.py "$U" --json "$LOG_DIR/${SAFE}_status.json" >/dev/null 2>&1
DONE=$(python3 -c "import json;d=json.load(open('$LOG_DIR/${SAFE}_status.json'));print(1 if d.get('done')==1 else 0)" 2>/dev/null || echo 0)
echo "[status] done=$DONE"
if [ "$DONE" = "1" ] && [ "$FORCE" = "0" ]; then echo "[SKIP] already done"; exit 0; fi

# 1. JPG → PNG
if compgen -G "$U/figs/*.jpg" >/dev/null || compgen -G "$U/figs/*.jpeg" >/dev/null || compgen -G "$U/figs/*.JPG" >/dev/null; then
  echo "[migrate] JPG -> PNG"
  ocrpipe figsize migrate "$U" --write --delete-jpg || { echo "[FAIL] migrate"; exit 10; }
fi

# 2. 候选
CAND="材料处理/$Y/$R/pdf_figures/figures.manifest.json"
if [ ! -f "$CAND" ]; then
  echo "[layout] $Y/$R"
  ocrpipe figsize layout "材料处理/$Y/$R" --detect --json >/dev/null || { echo "[FAIL] layout"; exit 11; }
  echo "[draft]"
  ocrpipe figsize draft "材料处理/$Y/$R" --pdf "OriginPDF/$Y/${Y}_${R}.pdf" >/dev/null || { echo "[FAIL] draft"; exit 12; }
  echo "[extract]"
  ocrpipe figsize extract "材料处理/$Y/$R/figures.draft.json" || { echo "[FAIL] extract"; exit 13; }
else
  echo "[candidates] reuse $CAND"
fi

# 3. 自动映射
echo "[map]"
python3 tools/figsize_automap.py "$U" --report --write || { echo "[FAIL] automap"; exit 20; }

# 4. plan（跳过未引用图）
echo "[plan]"
python3 tools/figsize_plan.py "$U" --write --keep-current --skip-unreferenced || { echo "[FAIL] plan"; exit 21; }

# 4a. 复合图回退
if ! python3 - "$U" <<'PY'
import json,sys
u=sys.argv[1]
m=json.load(open(f'{u}/figures.manifest.json'))
bad=[e['target'] for e in m['entries'] if e.get('status')=='missing_source']
print('[missing]', len(bad))
sys.exit(1 if bad else 0)
PY
then
  echo "[fallback-merge]"
  python3 tools/figsize_merge_fallback.py "$U" --report --write || true
  python3 tools/figsize_plan.py "$U" --write --keep-current --skip-unreferenced || { echo "[FAIL] plan(retry)"; exit 21; }
fi

# 4b. 不得留 None
python3 - "$U" <<'PY' || exit 22
import json,sys
u=sys.argv[1]
m=json.load(open(f'{u}/figures.manifest.json'))
bad=[e['target'] for e in m['entries'] if not (e.get('final',{}).get('width_cm') and e.get('final',{}).get('height_cm'))]
if bad:
    print('[FAIL] None final sizes:', bad); sys.exit(1)
print(f"[ok] manifest entries={len(m['entries'])} none-free")
PY

# 4c. 无扩展名 PNG 引用补 .png
python3 tools/figsize_fix_refs.py "$U" --write || true

# 5. 回填
echo "[apply]"
python3 tools/figsize_apply.py "$U" --write || { echo "[FAIL] apply"; exit 23; }

# 6. 本地 check
echo "[check]"
python3 tools/figsize_check.py "$U" || { echo "[FAIL] figsize_check"; exit 24; }

# 7. 外部 check（只把 errors 视为失败）
echo "[check-ext]"
make -s figsize-check-ext UNIT="$U" >"$LOG_DIR/${SAFE}_ext.json" 2>&1 || true
python3 - "$LOG_DIR/${SAFE}_ext.json" <<'PY' || exit 25
import json,sys
txt=open(sys.argv[1],encoding='utf-8',errors='ignore').read()
try:
    d,_=json.JSONDecoder().raw_decode(txt.lstrip())
    e=len(d.get('errors',[])); w=len(d.get('warnings',[]))
    print(f'[ext] errors={e} warnings={w}')
    if e: sys.exit(1)
except json.JSONDecodeError:
    print('[ext] could not parse JSON output (see log)'); sys.exit(1)
PY

# 8. 编译 + make check
if [ "$SKIP_COMPILE" -eq 0 ]; then
  echo "[compile] student"
  make -C "$U" student >"$LOG_DIR/${SAFE}_student.log" 2>&1 || { echo "[FAIL] student compile"; exit 30; }
  echo "[compile] teacher"
  make -C "$U" teacher >"$LOG_DIR/${SAFE}_teacher.log" 2>&1 || { echo "[FAIL] teacher compile"; exit 31; }
  echo "[make check]"
  make -C "$U" check >"$LOG_DIR/${SAFE}_check.log" 2>&1 || { echo "[FAIL] make check"; exit 32; }
fi

# 9. 摘要
python3 - "$U" <<'PY'
import json,sys
from collections import Counter
u=sys.argv[1]
m=json.load(open(f'{u}/figures.manifest.json'))
c=Counter(e.get('status') for e in m['entries'])
print(f"[SUMMARY] {u}: total={len(m['entries'])} " + " ".join(f'{k}={v}' for k,v in sorted(c.items())))
PY
echo "[DONE] $U"
