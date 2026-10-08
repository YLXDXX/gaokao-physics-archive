# 材料处理与 OCR 规范（PDF → Markdown 多引擎交叉验证）

本规范适用于高考真题制作中**以 JSON 为主、PDF/Docx 为辅**的校对与补全环节：
把每份原始 PDF 用**两个独立 OCR 引擎**（OvisOCR2、PaddleOCR-VL）各转一遍，
文字版再辅以 `pdftotext`，逐项交叉验证得到唯一主数据源 `merged.md`；
并从原 PDF **无损提取内嵌图**，为 JSON 缺图/复合图提供图片来源。

> 角色固定：**OvisOCR2 为底本，PaddleOCR-VL 作验证，`pdftotext` 作辅助**；
> 冲突时回**原 PDF（原图）**裁定。

---

## 一、处理目录

材料**统一**放在项目根目录的独立文件夹中，**不放进具体的 LaTeX 文档目录**：

```
材料处理/<年份>/<地区>/           # 与 试卷/<年份>/<地区>/ 一一对应，但相互分离
├── ovis/output.md + images/     # 引擎甲·底本
├── paddle/output.md + images/   # 引擎乙·验证
├── pdftotext.txt                # 旁证
├── merged.md                    # 最终主数据源
└── pdfimages/                   # 原 PDF 内嵌图无损提取 + manifest.json
```

> `材料处理/` 与各处 `svg-inkscape/`（Inkscape 生成物）均已在 `.gitignore` 中忽略，只保留本地。

若该年/地区**只有 `.docx` 没有 PDF**，用 pandoc 转 Markdown 作为参考（见第四节）。

---

## 二、三路转换（`tools/ocr_pipeline.sh`）

```bash
tools/ocr_pipeline.sh Docx/2026/2026_湖北.pdf 材料处理/2026/湖北
# 或（等价，根目录 Makefile 入口）：
make material PDF=Docx/2026/2026_湖北.pdf OUT=材料处理/2026/湖北
```

> **批量 / 全库**：`tools/ocr_pipeline.sh` 只处理**单份**。多卷或全库用
> `tools/ocr_batch.py`（分阶段、断点续跑、Ovis 模型单进程只加载一次），
> 或用**一键编排** `tools/ocr_pipeline_all.sh`（等价 `make material-batch`）——
> 后者自动启停 PaddleOCR-VL 服务并做端口健康检查，任一阶段失败即停。

脚本依次执行如下。**运行前须先启动 PaddleOCR-VL 服务**：

```bash
# ── 旁证：pdftotext（文字版 PDF；扫描版可失败） ──
pdftotext -layout "<源PDF>" "<处理目录>/pdftotext.txt"

# ── 引擎乙：PaddleOCR-VL（服务化） ──
./tools/paddlex_serve_start.sh                 # 先启动服务（默认 127.0.0.1:8203）
conda run -n BaiduPaddle python tools/PaddleOCR_PDF_to_md.py -i "<源PDF>" -o "<处理目录>/paddle"
./tools/paddlex_serve_stop.sh                  # 用完关闭，释放显存

# ── 引擎甲：OvisOCR2（底本） ──
conda run -n ovis_ocr python tools/pdf_to_md.py \
    --input "<源PDF>" --output "<处理目录>/ovis" \
    --model-path "$OVIS_MODEL" --enforce-eager

# ── 生成 merged.md（以 Ovis 为底本 + 三路差异记录） ──
python3 tools/material_merge.py "<处理目录>" --force

# ── 无损提取内嵌图 ──
python3 tools/pdf_extract_images.py "<处理目录>" --force
```

- OvisOCR2 环境：Anaconda `ovis_ocr`，模型目录由环境变量 `OVIS_MODEL` 指定（示例 `~/AI/ATH-MaaS/OvisOCR2/`）。
- PaddleOCR-VL 环境：Anaconda `BaiduPaddle`，服务默认 `127.0.0.1:8203`。
- `tools/check_material.py` 校验四要素（`ovis/output.md`、`paddle/output.md`、
  `pdftotext.txt`、`merged.md`）齐全非空、图片引用有效、底稿未漂移。

---

## 三、交叉验证规则

| 内容 | 裁定规则 |
| :--- | :--- |
| 文字 | 三路一致直接采用；两路一致取多数；互异回原 PDF 目视核对 |
| 公式 | 取 LaTeX 更完整、可编译、与原图逐符号一致者 |
| 表格 | 比对行列与单元格，跨页以不丢行、不串列者为准 |
| 图片 | 文字版优先原 PDF 无损提取；扫描版取更清晰者 |
| 数字/单位/上下标 | 双引擎 + pdftotext + 原图多方核对 |
| 无法裁定 | 以原 PDF（原图）为最终裁决，存疑记入 `merged.md` 头部与 `异常记录/<年份>.md` |

`merged.md` 是该卷的唯一主数据源，制作时**只读 `merged.md`**（必要时回原 PDF）。
JSON 与 `merged.md` 的差异属“语义校对”，**人工/agent 逐题核对**，不用脚本机械 diff。

---

## 四、Docx 参考（无 PDF 或需提取详解时）

`Docx/<年>/<年_地区>.docx` 含题干、答案与 `【详解】`。可用 pandoc 转为 Markdown 作参考：

```bash
pandoc -f docx -t markdown --extract-media=材料处理/2026/湖北/docx_media \
    "Docx/2026/2026_湖北.docx" -o 材料处理/2026/湖北/docx参考.md
```

> 注意：Word 中的公式常为 OMML/嵌入对象，pandoc 可能输出为 `.wmf` 图片而非 LaTeX。
> 因此**公式以 PDF 的 `merged.md` 为准**，Docx 主要提供**文字型详解**与结构参考。

---

## 五、图片处理

### 1. 来源优先级

1. **JSON 中的图片数据**（`JSON/.../tiku_images/…`）——首选，直接复制到 `figs/`；
2. **JSON 缺图** → 从对应 `.pdf` 用 `pdf_extract_images.py`（`pdfimages -all`）无损提取；
3. 纯矢量页（`pdfimages -list` 为 0 张）→ `pdftoppm -r 600 -png <PDF> <前缀>` 整页渲染后再裁
   （可直接用 `python3 tools/pdf_extract_images.py --root 材料处理 --render` 自动渲染落盘）；
4. 无 PDF 时，可用 Docx 内嵌媒体（`unzip` 解出 `word/media/`）。

### 2. 复合图拆分（`tools/recrop_figures.py`，依赖 splitpicture）

JSON 常把**多个子图合在一张图**里（如 2026 云南第 6、11、12、13 题）。要求
**裁剪一个核对一个，不做批量自动裁剪**。位图用 `splitpicture`（本项目不自研裁剪程序）：

```bash
python3 tools/recrop_figures.py scan  材料处理/2026/云南/pdfimages       # 分诊：列出多子图候选
python3 tools/recrop_figures.py split 材料处理/…/pdfimages/p6_0.jpg -o preview.png
python3 tools/recrop_figures.py preview 试卷/2026/云南/.recrop.json      # 只读叠加（绿=实裁框、黄=擦除框）
python3 tools/recrop_figures.py apply   试卷/2026/云南/.recrop.json      # 裁剪回填 figs/ + crop_compare/
```

- `splitpicture` 需在 `PATH`，或用 `SPLITPICTURE=/path/to/splitpicture` 指定；
  `detect --panels`（标签行分幅、自动排除 A/B/C/D）、`split --rects-file`（按框裁剪）。
- recipe（`试卷/<年>/<地区>/.recrop.json`）登记 `source` → `crops[rect,target]`；
  标签与图内文字同高时用 `erase`/`erase_labels` 先擦后裁。
- **必须打开 `crop_compare/*.png` 逐张核对**（左＝裁剪输入、右＝回填子图）；纯去白边不生成。
- `make check` 的 `check_recrop.py` 校验 recipe 与 `figs/` 结构/尺寸/文件头一致。
- **SVG 复合图**：在 Inkscape 中人工拆分导出子图（本项目暂不做自动矢量拆分）。
- 拆分后按 `figs/<题号><子图字母>.<ext>` 命名回填；子图**不得含**自带编号标签
  （`甲/乙/丙`、`A/B/C/D`），编号由 `ChoiceQuestion` 自动生成。
- **无法无损拆分**的复合图（子图相互连接、无空白带、元素交织）：允许以**原图整体呈现**，
  但须在 `异常记录/<年份>.md` 登记（见 `高考物理真题制作规范.md` 第五节）；不得 TikZ 重绘。

> `splitpicture` 自身的完整用法（三种检测模式 `--panels/--options/--detect`、标签检测
> 与 `--erase-labels`、CLI 与 GUI、难例调参）见 [`tools/splitpicture使用说明.md`](tools/splitpicture使用说明.md)。

### 3. 去标签与去白边

- 子图带 `图甲/图1/A–D` 等标签时，裁剪时应去掉（宏会自动编号）。
- 四周多余白边可裁去，保持版面紧凑。
- 解析用图命名 `<题号>_an.<ext>`（多张用 `_an1/_an2`），置于该卷 `figs/`。

### 4. TikZ 重绘：严禁转换中引入，人工重绘须登记核对

- 转换过程**严禁**用 TikZ 重绘图片（即使很简单）；一律用 JSON / PDF 原图。
- 确需重绘者由**人工手绘**并放入该卷 `TikZ/`（一张图一个 `.tex` → 编译为 PDF，
  正文用 `\onepicture{TikZ/<名>.pdf}` 引用），如 2026 湖北第 4 题。
- 重绘须在 `TikZ/tikz_sources.json` **登记原图**，并 `make tikz-compare` 生成
  `tikz_compare/<文档>_重绘前后.png` **逐张核对**；登记格式见 `tools/README.md`。
  `make check` 的 `check_tikz.py` 校验登记一致性。
- **标准做法**：`TikZ/<名>.tex` 与 `figs/<名>` **同名**；`original` 原图已在 `figs/` 时
  直接指向 `试卷/<年>/<地区>/figs/<名>.png`，**无需再建 `TikZ/originals/`**（仅当原图不在
  `figs/` 时才另存 `originals/`）。**只上传 `TikZ/*.tex`（未登记、未接入）不推荐**：
  `check_tikz.py` 会告警，`tikz-compare` 默认仍出图，但文件名**必须与 `figs/` 同名**。

---

## 六、异常记录

材料处理与校对中发现的问题（缺图、缺详解、公式疑误、题文矛盾、复合图未拆、
回忆版、理综卷含非物理题、OCR 冲突无法裁定等），一律记入 `异常记录/<年份>.md`。
