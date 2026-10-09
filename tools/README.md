# tools 脚本索引

本项目所有脚本集中在 `tools/`，供**真题制作**与**材料处理**使用。根目录 `Makefile`
封装了常用入口，见 `README.md`「编译方法」。

## 一、制作主流程

| 脚本 | 用途 | 典型用法 |
| :--- | :--- | :--- |
| `json_to_tex.py` | 由平台 JSON 生成某卷 LaTeX **初稿** + 图片素材（复制到 `试卷/…/figs/`；HTML/公式经 `html2latex.py` 转换）。支持：缺 memo 占位、非选择题自动 `\jdanswer`、同题多图 `\twopicture`、图片选项 `\fourchoices[ispicture=true]`、`--paper-type` 卷级标记；`--renumber` 重编号并写 `%% sourceNumbers`（`check_meta`/`check_review` 据此映射回原题号） | `python3 tools/json_to_tex.py JSON/2026/2026_湖北.json` |
| `html2latex.py` | HTML（含 MathJax 公式）→ LaTeX 的 **DOM 转换器**（由 `json_to_tex.py` 调用；移植自 texgen，正确处理上下标、表格、公式片段合并与字符映射） | 见 `test_html2latex.py` |
| `check_paper.py` | 试卷**规范自查**：文档骨架（含两版开关 `\gkver`）、13 项元数据顺序、图片命令、引用标签、图片存在、每题基本详解 | `python3 tools/check_paper.py 试卷/2025/湖北/湖北.tex` |
| `check_meta.py` | **元数据 ↔ 平台 JSON 逐字段一致**（防转换漂移，含选择题 `%% answer`） | `python3 tools/check_meta.py 试卷/2000/上海/上海.tex` |
| `check_formula_numbers.py` | **解析公式编号检查**：只识别公式编号（过滤 `①过程`、`图象为②`、小问标签），要求 ①–⑳ 从 ① 起连续、无悬空引用 | `python3 tools/check_formula_numbers.py 试卷/` |
| `check_answers.py` | **非选择题答案对应**：必须有 `\jdanswer`/`\tkanswer`；计算题比对小问数与 `\jdanswer` 项数，实验题（typeId=4）免项数比对（答案可手动编号） | `python3 tools/check_answers.py 试卷/` |
| `check_units.py` | **PhyUnit 宏检查**：`\Uxxx` 是否均已定义；`--suggest` 给出裸单位建议宏 | `python3 tools/check_units.py 试卷/` |
| `tex_to_json.py` | 由成品 `.tex` **反向抽取档案 JSON**（元数据/题干/答案/详解），`--compare` 与平台 JSON 核对 | `python3 tools/tex_to_json.py 试卷/2000/上海/上海.tex --compare JSON/2000/2000_上海.json` |
| `check_content.py` | 试卷**内容书写检查**：裸单位（应用 PhyUnit）、图片充当公式；并提示段落未分行 / 中英文间距（见 `LaTeX_format_ReadMe.md`） | `python3 tools/check_content.py 试卷/` |
| `check_layout_cmds.py` | **版面微调命令检查**：禁止原生 `\newpage`/`\clearpage`/`\vfill`/`\vfil`/`\hfil`，应改用仅学生版生效的 `\gknewpage` 等（见 `LaTeX_format_ReadMe.md` 第 34 条） | `python3 tools/check_layout_cmds.py 试卷/` |
| `textfix/` | **共性问题正则修正模块**（数字间全角冒号、行内公式连字符、`\dfrac`→`\frac`），默认只检查、`--write` 写回 | `python3 tools/textfix/textfix.py --check 试卷/` |
| `tex_links.py` | 为各卷目录创建指向根公共文件（`gaokaozhenti.cls`/`PhyUnit.sty`/`ChoiceQuestion.sty`/`package`）的相对软链接（各卷 Makefile 的 `make`/`student`/`teacher` 会**自动执行**，便于 TeXStudio 直接编译） | `python3 tools/tex_links.py` |
| `gen_index.py` | **索引/进度生成与共享库**：扫描 `试卷/`，生成 `试卷/<年>/README.md`、刷新 README 进度概要、回填 `进度记录.md` 题数（`--check` 校验） | `python3 tools/gen_index.py --write`（`make index`） |
| `review_to_ledger.py` | 由**复核结果 JSON** 生成/更新 `异常记录/<年>.md` 台账（按 `地区/题号/类别/问题` 去重、更新状态；按状态并入对应分区、状态变化时移动分区） | `python3 tools/review_to_ledger.py 复核结果.json --write` |
| `check_docs_text.py` | **文档体检**：扫描根 / `docs/` / `tools/` 的 Markdown，检查过时 `cd` 用法与失效相对链接 | `python3 tools/check_docs_text.py` |
| `check_docs.py` | **文档一致性校验**：`进度记录.md` ↔ `试卷/` 双向一致、状态取值、题数相符、年份索引与 `异常记录/<年>.md` 表头/状态规范及**统一结构**（制作说明 + 状态分区顺序，已解决置末） | `python3 tools/check_docs.py`（`make check-docs`，已接入 `make check`） |
| `status.py` | **各年份进度概要**：套数、题数、进度表“已完成”计数 | `python3 tools/status.py`（`make progress`） |

> **并行编译包装**：`bin/inkscape` 用 `flock` 串行化 Inkscape 调用，规避 `make -jN` 并发时
> `Gio::DBus::Error` 崩溃；各卷 Makefile 已把 `tools/bin` 加入 `PATH`，无需手动调用
> （无 `flock` 的系统退化为直接调用，此时应串行编译）。

## 二、材料处理（PDF → Markdown / 图片）

> 角色固定：**OvisOCR2 底本 + PaddleOCR-VL 验证 + pdftotext 旁证**；详见
> [`../材料处理与OCR规范.md`](../材料处理与OCR规范.md)。

| 脚本 | 用途 | 典型用法 |
| :--- | :--- | :--- |
| `ocr_pipeline.sh` | 一键三路转换 + 生成 `merged.md` + 无损提图（**单份**） | `tools/ocr_pipeline.sh Docx/2026/2026_湖北.pdf 材料处理/2026/湖北` |
| `ocr_batch.py` | **批量**材料处理驱动（`list`/`status`/`pdftotext`/`paddle`/`ovis`/`merge`/`extract`，可断点续跑；Ovis 单进程只加载一次模型） | `python3 tools/ocr_batch.py status` |
| `ocr_pipeline_all.sh` | **全库一键编排**：pdftotext → Paddle（自动启停+健康检查）→ Ovis → merged → 提图；失败即停、断点续跑 | `bash tools/ocr_pipeline_all.sh`（或 `make material-batch`） |
| `pdf_to_md.py` | 引擎甲 **OvisOCR2**（底本） | 见 `ocr_pipeline.sh` |
| `PaddleOCR_PDF_to_md.py` | 引擎乙 **PaddleOCR-VL**（验证，服务化） | 见 `ocr_pipeline.sh` |
| `paddlex_serve_start.sh` / `paddlex_serve_stop.sh` | 启动 / 关闭 PaddleOCR-VL 服务（默认端口 8203） | `./tools/paddlex_serve_start.sh` |
| `material_merge.py` | 以 Ovis 为底本合并三路，生成/校验 `merged.md`（含底稿缺失/漂移守卫） | `python3 tools/material_merge.py --root 材料处理` |
| `pdf_extract_images.py` | `pdfimages -all` **无损提取**原 PDF 内嵌图到 `pdfimages/` + `manifest.json`；纯矢量页可加 `--render` 用 `pdftoppm` 整页渲染 | `python3 tools/pdf_extract_images.py --root 材料处理 --render` |
| `check_material.py` | 材料**四要素**（ovis/paddle/pdftotext/merged）完整性、图片引用有效、底稿漂移、manifest 文件齐全、纯矢量页清单 | `python3 tools/check_material.py` |

环境（可用环境变量覆盖，见脚本头）：

- `CONDA_ROOT=/opt/anaconda`；`OVIS_ENV=ovis_ocr`、`PADDLE_ENV=BaiduPaddle`；
- `OVIS_MODEL`（OvisOCR2 模型目录，示例 `~/AI/ATH-MaaS/OvisOCR2`）；
- PaddleOCR-VL pipeline：`PADDLE_PIPELINE`（示例 `~/myservice/OCR/PaddleOCR/my_PaddleOCR-VL-1.6.yaml`）；
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

> **splitpicture 的完整用法（三种检测模式、标签擦除、CLI/GUI、调参与难例）见
> [`splitpicture使用说明.md`](splitpicture使用说明.md)。**

## 四、TikZ 重绘核对

| 脚本 | 用途 |
| :--- | :--- |
| `tikz_compare.py` | 生成「左＝原图 / 右＝重绘 TikZ」对比图到 `tikz_compare/`，供人工逐张核对；**默认**也为**未接入正文/未登记**的 `TikZ/*.tex`（“只上传 TikZ 文件夹”）出图（原图按 `TikZ/originals/<名>` → `figs/<名>` **同名**自动推断，`.svg` 自动渲染）；`--no-orphans` 可只处理已接入的 |
| `check_tikz.py` | 校验 `TikZ/tikz_sources.json` 的登记与 `TikZ/*.pdf` 引用一致；并提示**已上传但未被引用、也未登记**的 `TikZ/*.tex`（不推荐做法；若同名 `figs/` 原图缺失会额外告警） |

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
  **原图已在 `figs/` 时直接指向** `试卷/<年>/<地区>/figs/<名>.png` 即可（`figs/` 已入库，
  **无需**再建 `TikZ/originals/`）。仅当原图不在 `figs/` 时，才把原图**随源码入库**到该卷
  `TikZ/originals/<名>.png`（原为矢量图时用 `pdftoppm`/Inkscape 渲染为 PNG）再指向它。
- 命名：`TikZ/<名>.tex` 建议与 `figs/<名>` **同名**；有登记且正文已接入时可用其它名，但不推荐。

## 五、检查项汇总

**每卷目录** `make check` 按下列顺序执行（与各卷 `Makefile` 的 `check` 目标一致）：

1. `check_paper.py`（结构 / 13 项元数据 / 图片命令 / 标签 / 答案；并提示 `\onepicture` 有 label 无 num、同题重复引用同一图）；
2. `check_content.py`（内容：裸单位 / 图片公式 / 数学模式内 CJK / `\mathrm{汉字}`，并提示段落分行、中英文间距）；
3. `textfix/textfix.py --check`（共性问题：全角冒号、公式连字符、en/em 破折号、`\dfrac`）；
4. `check_layout_cmds.py`（版面微调命令：禁止原生断页 / 撑开命令）；
5. `check_glyphs.py`（编译日志缺字 `Missing character`，如 `\mathrm` 内汉字丢字）；
6. `check_review.py`（成品跨项复查：解析引图必在、选择题三处答案一致、与 JSON 答案一致、`\ref` 已定义、重复标签、公式编号悬空、占位详解计数）；
7. `check_meta.py`（元数据逐字段与平台 JSON 一致）；
8. `check_answers.py`（非选择题答案命令与小问对应）；
9. `check_formula_numbers.py`（解析公式编号 ①②③… 连续、无悬空引用）；
10. `check_units.py`（`\Uxxx` 是否已在 `PhyUnit.sty` 定义）。

**根目录** `make check` 在各卷之上再执行：

11. `check_tikz.py`（TikZ 原图登记 / 未接入的“孤儿源” / 引用却缺 `.tex` 源）；
12. `check_recrop.py`（裁剪 recipe；并提示孤儿 figs）；
13. `check_material.py`（材料完整性：四要素 / 图片引用 / manifest 文件齐全 / 纯矢量页清单）；
14. `check_glyphs.py`（全库编译日志缺字兜底）；
15. `check_review.py`（全库成品跨项复查兜底）；
16. `check_docs.py`（进度 / 年份索引 / 异常记录 文档一致性，`make check-docs`）；
17. `check_docs_text.py`（文档体检：过时 `cd` 用法、失效相对链接）。

> `make check YEAR=2000` 只查该年；`make check-changed` 只查工作树**未提交**改动
> （审查他人 PR 分支用 `make pr-check`）；`make ci` 抽样构建 + 全量自查。

## 六、tools 单元测试

```bash
make tools-test
# 等价于：
python3 -m unittest tools.textfix.test_textfix tools.test_ocr_batch \
    tools.test_check_content tools.test_check_recrop tools.test_check_tikz \
    tools.test_tikz_compare tools.test_match_figures tools.test_pdf_extract_images \
    tools.test_recrop_figures tools.test_gen_index tools.test_json_to_tex \
    tools.test_html2latex tools.test_check_meta tools.test_check_answers \
    tools.test_check_units tools.test_check_formula_numbers \
    tools.test_review_to_ledger tools.test_tex_to_json
```

覆盖正则规则（含裸单位）/ 批量映射 / 裁剪 recipe / TikZ 登记 / 图片匹配 / 无损提图 /
裁剪回填 / 元数据·JSON 一致性 / 非选择题答案对应 / 单位宏 / 反向抽取 / 索引生成 /
HTML→LaTeX 转换（公式片段合并、上下标、表格、图片命名）等纯函数与端到端逻辑。
