# 材料处理与 OCR 规范（PDF → Markdown 多引擎交叉验证）

本规范适用于高考真题制作中**以 JSON 为主、PDF 为辅**的校对与补全环节：
把每份原始 PDF 用**两个独立 OCR 引擎**（OvisOCR3、PaddleOCR-VL）各转一遍，
文字版再辅以 `pdftotext`，逐项交叉验证得到唯一主数据源 `merged.md`；
并从原 PDF **无损提取内嵌图**，为 JSON 缺图/复合图提供图片来源。

> 角色固定：**OvisOCR3 为底本，PaddleOCR-VL 作验证，`pdftotext` 作辅助**；
> 冲突时回**原 PDF（原图）**裁定。

---

## 一、处理目录

材料**统一**放在项目根目录的独立文件夹中，**不放进具体的 LaTeX 文档目录**：

```
材料处理/<年份>/<地区>/           # 与 试卷/<年份>/<地区>/ 一一对应，但相互分离
├── source.json                  # 源 PDF 路径/页数/sha256/文字版判定
├── ovis/output.md + images/     # 引擎甲·底本（OvisOCR3）
├── ovis/raw|structured|layout|pages/  # 逐页原始响应/规范化版面/纯版面/页 Markdown
├── paddle/output.md + images/   # 引擎乙·验证（PaddleOCR-VL）
├── paddle/raw|structured|pages/ # 逐页版面框与规范化 Markdown
├── pdftotext.txt                # 旁证
├── merged.md                    # 最终主数据源
└── pdfimages/                   # 原 PDF 内嵌图无损提取 + manifest.json
```

> `材料处理/` 与各处 `svg-inkscape/`（Inkscape 生成物）均已在 `.gitignore` 中忽略，只保留本地。

若该年/地区**缺 PDF**，仅依 JSON 制作，并在 `异常记录/<年份>.md` 登记；补齐 PDF 后重做材料。

---

## 二、三路转换（`ocrpipe`）

```bash
# 单卷（等价根目录 Makefile 入口）
make material PDF=OriginPDF/2026/2026_湖北.pdf OUT=材料处理/2026/湖北

# 或直接用统一流水线（Paddle 自动启停、逐页断点续跑）
ocrpipe run \
    -c ocr_pipeline.json -i OriginPDF/2026/2026_湖北.pdf \
    -o 材料处理/2026/湖北 --auto-serve
```

> **批量 / 全库**：`make material-batch ARGS="--auto-serve"`（等价
> `ocrpipe batch -c ocr_pipeline.json --root 材料处理`）。
> 分阶段、断点续跑、Paddle 自动分块与自动启停；筛选改用 `--only 2026/湖北`
> （旧的 `--year/--region` 已移除）。中断后重复同一命令即可续跑。

流水线按 `text → images → paddle → ovis → merge → check` 顺序执行：

```bash
# ── text：pdftotext 旁证 + source.json ──
pdftotext -layout "<源PDF>" "<处理目录>/pdftotext.txt"

# ── images：无损提取内嵌图（文字版 PDF） ──
ocrpipe images --pdf "<源PDF>" --out "<处理目录>/pdfimages" --quiet

# ── paddle：PaddleOCR-VL（服务化；--auto-serve 自动启动/关闭） ──
#    逐页保存 paddle/raw/page_N.json（prunedResult）与 structured/pages

# ── ovis：OvisOCR3（底本） ──
#    逐页保存 ovis/raw|structured|layout|pages 与 Markdown

# ── merge：以 Ovis 为底本 + 三路差异记录 ──
ocrpipe merge "<处理目录>" --force

# ── check：四要素 + 逐页源数据 + 图片引用 + 底稿漂移 ──
ocrpipe check "<处理目录>"
```

- OvisOCR3：沿用 Anaconda `ovis_ocr` 环境，模型 `/home/shui/AI/ATH-MaaS/OvisOCR3`；
  可用 `OVIS_MODEL` 覆盖。PyMuPDF/Pillow/requests/vllm 依赖原环境已具备。
- PaddleOCR-VL：Anaconda `BaiduPaddle`，服务默认 `127.0.0.1:8203`。
- 两个引擎共用 GPU，**不要同时运行**；流水线已强制规范阶段顺序。
- `ocrpipe check` 校验四要素（`ovis/output.md`、`paddle/output.md`、
  `pdftotext.txt`、`merged.md`）齐全非空、图片引用有效、底稿未漂移，
  并在 `ovis/manifest.json` / `paddle/manifest.json` 存在时强制逐页
  `raw/structured/layout/pages` 源数据齐全（旧格式只提示升级）。

---

## 三、交叉验证规则

| 内容 | 裁定规则 |
| :--- | :--- |
| 文字 | 三路一致直接采用；两路一致取多数；互异回原 PDF 目视核对 |
| 公式 | 取 LaTeX 更完整、可编译、与原图逐符号一致者 |
| 表格 | 比对行列与单元格，跨页以不丢行、不串列者为准 |
| 图片 | 文字版优先原 PDF 无损提取；扫描版取更清晰者；bbox 以 `ovis/structured` 或 Paddle `layout_det_res` 为准 |
| 数字/单位/上下标 | 双引擎 + pdftotext + 原图多方核对 |
| 无法裁定 | 以原 PDF（原图）为最终裁决，存疑记入 `merged.md` 头部与 `异常记录/<年份>.md` |

`merged.md` 是该卷的唯一主数据源，制作时**只读 `merged.md`**（必要时回原 PDF）。
JSON 与 `merged.md` 的差异属“语义校对”，**人工/agent 逐题核对**，不用脚本机械 diff。

> 扫描件/低清 PDF 中的图只作**尺寸参考**；JSON 清晰图不被扫描图替换，详见 `图片尺寸处理规范.md`。

---

## 四、PDF 参考与详解

本仓库已统一只保留源 PDF（`OriginPDF/<年>/<年_地区>.pdf`），不再保存 `.docx`。
题干、答案与 `【详解】` 一律以原 PDF 的 `merged.md` 为主数据源；
PDF 无文字层或详解缺失时，按原 PDF 页面/图像人工核对，并在
`异常记录/<年份>.md` 登记，不再依赖 Word 文档。

---

## 五、图片处理

### 1. 来源优先级

1. **JSON 中的图片数据**（`JSON/.../tiku_images/…`）——首选，直接复制到 `figs/`；
2. **JSON 缺图** → 从对应 `.pdf` 用 `ocrpipe images`（`pdfimages -all`）无损提取；
   Paddle 的 `paddle/structured` 与 OvisOCR3 的 `ovis/structured` 可用于按 bbox 复核/补裁；
3. 纯矢量页（`pdfimages -list` 为 0 张）→ `pdftoppm -r 600 -png <PDF> <前缀>` 整页渲染后再裁
   （可直接用 `ocrpipe images --root 材料处理 --render` 自动渲染落盘）；
4. 无 PDF 时不从其它格式补图；缺图按 `异常记录/<年份>.md` 登记，待补齐 PDF 后重做。

### 2. 复合图拆分（`ocrpipe recrop`，依赖 splitpicture）

JSON 常把**多个子图合在一张图**里（如 2026 云南第 6、11、12、13 题）。要求
**裁剪一个核对一个，不做批量自动裁剪**。位图用 `splitpicture`（本项目不自研裁剪程序）：

```bash
ocrpipe recrop scan  材料处理/2026/云南/pdfimages       # 分诊：列出多子图候选
ocrpipe recrop split 材料处理/…/pdfimages/p6_0.jpg -o preview.png
ocrpipe recrop preview 试卷/2026/云南/.recrop.json      # 只读叠加（绿=实裁框、黄=擦除框）
ocrpipe recrop apply   试卷/2026/云南/.recrop.json      # 裁剪回填 figs/ + crop_compare/
```

- `splitpicture` 需在 `PATH`，或用 `SPLITPICTURE=/path/to/splitpicture` 指定；
  `detect --panels`（标签行分幅、自动排除 A/B/C/D）、`split --rects-file`（按框裁剪）。
- recipe（`试卷/<年>/<地区>/.recrop.json`）登记 `source` → `crops[rect,target]`；
  标签与图内文字同高时用 `erase`/`erase_labels` 先擦后裁。
- **必须打开 `crop_compare/*.png` 逐张核对**（左＝裁剪输入、右＝回填子图）；纯去白边不生成。
- `make check` 的 `ocrpipe check-recrop` 校验 recipe 与 `figs/` 结构/尺寸/文件头一致。
- **SVG 复合图**：在 Inkscape 中人工拆分导出子图（本项目暂不做自动矢量拆分）。
- **ABCD 图片选项、图甲乙丙丁、图 abcd 等必须逐张拆成独立文件**；不得把多个选项或子图
  拼在一张图里。
- 拆分后按 `figs/<题号><子图字母>.<ext>` 命名回填；子图**不得含**自带编号标签
  （`甲/乙/丙`、`A/B/C/D`）、图题或题注，编号与标题由 `ChoiceQuestion`/正文自动生成。
- **无法无损拆分**的复合图（子图相互连接、无空白带、元素交织）：允许以**原图整体呈现**，
  但须在 `异常记录/<年份>.md` 登记（见 `高考物理真题制作规范.md` 第五节）；不得 TikZ 重绘。

> `splitpicture` 自身的完整用法（三种检测模式 `--panels/--options/--detect`、标签检测
> 与 `--erase-labels`、CLI 与 GUI、难例调参）见 [`tools/splitpicture使用说明.md`](tools/splitpicture使用说明.md)。

### 3. 去标签、去图题与去白边

- 子图带 `图甲/图1/A–D` 等标签、图题或题注时，裁剪时应去掉（标题与编号由宏/正文生成）。
- 去掉后正文引用一律用 `\ref{标签}` 自动生成序号，**不得手写“图甲/图1/图A”**；
  `\ref` 前后留一个空格（或 `~`）。
- 四周多余白边可裁去，保持版面紧凑。
- 图片明显过宽、过高、过小、超版心或拉伸变形时，按 `图片尺寸处理规范.md` 修正；
  不能修正的记入 `异常记录/<年份>.md`（类别 `图片尺寸`）。
- 解析用图命名 `<题号>_an.<ext>`（多张用 `_an1/_an2`），置于该卷 `figs/`。

### 4. TikZ 重绘：严禁转换中引入，人工重绘须登记核对

- 转换过程**严禁**用 TikZ 重绘图片（即使很简单）；一律用 JSON / PDF 原图。
- 确需重绘者由**人工手绘**并放入该卷 `TikZ/`（一张图一个 `.tex` → 编译为 PDF，
  正文用 `\onepicture{TikZ/<名>.pdf}` 引用），如 2026 湖北第 4 题。
- 重绘须在 `TikZ/tikz_sources.json` **登记原图**，并 `make tikz-compare` 生成
  `tikz_compare/<文档>_重绘前后.png` **逐张核对**；登记格式见 `tools/README.md`。
  `make check` 的 `ocrpipe check-tikz` 校验登记一致性。
- **标准做法**：`TikZ/<名>.tex` 与 `figs/<名>` **同名**；`original` 原图已在 `figs/` 时
  直接指向 `试卷/<年>/<地区>/figs/<名>.png`，**无需再建 `TikZ/originals/`**（仅当原图不在
  `figs/` 时才另存 `originals/`）。**只上传 `TikZ/*.tex`（未登记、未接入）不推荐**：
  `ocrpipe check-tikz` 会告警，`tikz-compare` 默认仍出图，但文件名**必须与 `figs/` 同名**。

---

## 六、异常记录

材料处理与校对中发现的问题（缺图、缺详解、公式疑误、题文矛盾、复合图未拆、
回忆版、理综卷含非物理题、OCR 冲突无法裁定等），一律记入 `异常记录/<年份>.md`。

- **超长填空横线导致的 Ovis 退化**：含连续长横线的页面（如核反应式填空）可能让
  OvisOCR3 重复生成海量 `\_`，表现为 `finish_reason=length`、`ovis/manifest.json`
  状态 `partial`、`ocrpipe check` 失败。处理顺序：
  1. 对该卷按较低 DPI（如 `--dpi 200`）重渲染并 `--force-stage ovis` 重跑
     ovis→merge→check（实测可消除循环）；
  2. 仍失败时，用临时配置同时提高 `ovis.max_tokens` 与 `model.max_model_len`
     再试（模型文本上限 262144）；
  3. **不得手改** OCR 产物；修复后核对 `merged.md` 与页序，并记入
     `异常记录/<年份>.md`（类别 `其它`，写明原始 PDF 与所用 DPI）。
