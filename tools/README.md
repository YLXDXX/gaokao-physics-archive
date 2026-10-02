# tools 脚本索引

本项目所有脚本集中在 `tools/`，供**真题制作**与**材料处理**使用。根目录 `Makefile`
封装了常用入口，见 `README.md`「编译方法」。

## 一、制作主流程

| 脚本 | 用途 | 典型用法 |
| :--- | :--- | :--- |
| `json_to_tex.py` | 由平台 JSON 生成某卷 LaTeX **初稿** + 图片素材（复制到 `试卷/…/figs/`），并把 JSON 基础材料 markdown 写到 `材料处理/<年>/<地区>/` | `python3 tools/json_to_tex.py JSON/2026/2026_湖北.json` |
| `check_paper.py` | 试卷**规范自查**：文档骨架（含两版开关 `\gkver`）、13 项元数据顺序、图片命令、引用标签、图片存在、每题基本详解 | `python3 tools/check_paper.py 试卷/2025/湖北/湖北.tex` |
| `check_content.py` | 试卷**内容书写检查**：裸单位（应用 PhyUnit）、图片充当公式；并提示段落未分行 / 中英文间距（见 `LaTeX_format_ReadMe.md`） | `python3 tools/check_content.py 试卷/` |
| `check_layout_cmds.py` | **版面微调命令检查**：禁止原生 `\newpage`/`\clearpage`/`\vfill`/`\vfil`/`\hfil`，应改用仅学生版生效的 `\gknewpage` 等（见 `LaTeX_format_ReadMe.md` 第 34 条） | `python3 tools/check_layout_cmds.py 试卷/` |
| `textfix/` | **共性问题正则修正模块**（数字间全角冒号、行内公式连字符、`\dfrac`→`\frac`），默认只检查、`--write` 写回 | `python3 tools/textfix/textfix.py --check 试卷/` |
| `tex_links.py` | 为各卷目录创建指向根公共文件（`gaokaozhenti.cls`/`PhyUnit.sty`/`ChoiceQuestion.sty`/`package`）的相对软链接 | `python3 tools/tex_links.py` |

## 二、材料处理（PDF → Markdown / 图片）

> 角色固定：**OvisOCR2 底本 + PaddleOCR-VL 验证 + pdftotext 旁证**；详见
> [`../材料处理与OCR规范.md`](../材料处理与OCR规范.md)。

| 脚本 | 用途 | 典型用法 |
| :--- | :--- | :--- |
| `ocr_pipeline.sh` | 一键三路转换 + 生成 `merged.md` + 无损提图（**单份**） | `tools/ocr_pipeline.sh Docx/2026/2026_湖北.pdf 材料处理/2026/湖北` |
| `ocr_batch.py` | **批量**材料处理驱动（`list`/`status`/`pdftotext`/`paddle`/`ovis`/`merge`/`extract`，可断点续跑；Ovis 单进程只加载一次模型） | `python3 tools/ocr_batch.py status` |
| `pdf_to_md.py` | 引擎甲 **OvisOCR2**（底本） | 见 `ocr_pipeline.sh` |
| `PaddleOCR_PDF_to_md.py` | 引擎乙 **PaddleOCR-VL**（验证，服务化） | 见 `ocr_pipeline.sh` |
| `paddlex_serve_start.sh` / `paddlex_serve_stop.sh` | 启动 / 关闭 PaddleOCR-VL 服务（默认端口 8203） | `./tools/paddlex_serve_start.sh` |
| `material_merge.py` | 以 Ovis 为底本合并三路，生成/校验 `merged.md`（含底稿缺失/漂移守卫） | `python3 tools/material_merge.py --root 材料处理` |
| `pdf_extract_images.py` | `pdfimages -all` **无损提取**原 PDF 内嵌图到 `pdfimages/` + `manifest.json` | `python3 tools/pdf_extract_images.py --root 材料处理` |
| `check_material.py` | 材料**四要素**（ovis/paddle/pdftotext/merged）完整性、图片引用有效、底稿漂移 | `python3 tools/check_material.py` |

环境（可用环境变量覆盖，见脚本头）：

- `CONDA_ROOT=/opt/anaconda`；`OVIS_ENV=ovis_ocr`、`PADDLE_ENV=BaiduPaddle`；
- `OVIS_MODEL=/home/shui/AI/ATH-MaaS/OvisOCR2`；
- PaddleOCR-VL pipeline：`PADDLE_PIPELINE`（默认 `/home/shui/myservice/OCR/PaddleOCR/my_PaddleOCR-VL-1.6.yaml`）；
- poppler：`pdftotext` / `pdfimages`。

## 三、多子图裁剪（依赖外部 **splitpicture**）

| 脚本 | 用途 |
| :--- | :--- |
| `recrop_figures.py` | 按 recipe（`.recrop.json`）用 splitpicture 裁剪内嵌图 → 回填 `figs/`；并生成 `crop_compare/` 前后对比、`crop_preview/` 只读叠加预览 |
| `match_figures.py` | 旧 `figs/*` → 源内嵌图/裁剪框 匹配草表（分诊，仅候选） |
| `check_recrop.py` | 校验 `.recrop.json` 的 source/rect/target 与 `figs/` 结构/尺寸/文件头一致 |

常用：`scan`（分诊）→ `split`/`labels`（预览框）→ 写 recipe → `preview`（叠加核对）
→ `apply`（裁剪回填）→ 打开 `crop_compare/` 逐张核对。
`splitpicture` 需在 `PATH`，或用 `SPLITPICTURE=/path/to/splitpicture` 指定。

## 四、TikZ 重绘核对

| 脚本 | 用途 |
| :--- | :--- |
| `tikz_compare.py` | 生成「左＝原图 / 右＝重绘 TikZ」对比图到 `tikz_compare/`，供人工逐张核对 |
| `check_tikz.py` | 校验 `TikZ/tikz_sources.json` 的登记与 `TikZ/*.pdf` 引用一致 |

登记文件 `试卷/<年>/<地区>/TikZ/tikz_sources.json` 格式：

```json
{
  "entries": [
    { "tikz": "01", "original": "试卷/2026/湖北/TikZ/originals/43162.png",
      "note": "2026 湖北第 4 题 v–t 图，人工重绘" }
  ]
}
```

- `tikz`：`TikZ/<tikz>.pdf` 的文件名（去扩展名）；
- `original`：相对项目根的原图路径（**必须存在**）；确无原题图者写 `null`（如自编题）。
  为让 `make check` 在无 `JSON/`、`材料处理/` 的克隆环境中也能通过，建议把原图**随源码入库**：
  放在该卷 `TikZ/originals/<名>.png`（原为矢量图时用 `pdftoppm`/Inkscape 渲染为 PNG），
  再在 `tikz_sources.json` 指向它。

## 五、检查项汇总

每卷目录 `make check` 依次执行：

1. `check_paper.py`（结构 / 13 项元数据 / 图片命令 / 标签 / 答案）；
2. `check_content.py`（内容：裸单位 / 图片公式，并提示段落分行、中英文间距）；
3. `textfix/textfix.py --check`（共性问题：全角冒号、公式连字符、`\dfrac`）；
4. `check_layout_cmds.py`（版面微调命令：禁止原生断页 / 撑开命令）。

根目录 `make check` 在各卷之上再执行：

5. `check_tikz.py`（TikZ 原图登记）；
6. `check_recrop.py`（裁剪 recipe）；
7. `check_material.py`（材料完整性）。

## 六、tools 单元测试

```bash
make tools-test
# 等价于：
python3 -m unittest tools.textfix.test_textfix tools.test_check_recrop \
    tools.test_check_tikz tools.test_match_figures \
    tools.test_pdf_extract_images tools.test_recrop_figures
```

覆盖正则规则 / 裁剪 recipe / TikZ 登记 / 图片匹配 / 无损提图 / 裁剪回填等纯函数与端到端逻辑。
