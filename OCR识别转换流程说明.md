# OCR 识别转换流程说明（OvisOCR3 + PaddleOCR-VL）

本文是 `材料处理规范.md` 的配套技术文档，说明本项目当前的 **PDF → Markdown + 版面源数据** 转换程序：
为什么升级到 OvisOCR3、程序如何封装、产物是什么、如何大批量运行、中断后如何续跑，以及如何把这套程序
迁移到 `gaokao-physics-archive`、`QJPhysics` 等其它项目。

> **本项目适配（gaokao-physics-archive）**：统一入口仍为
> `python3 -m tools.ocr_pipeline`，配置为根目录 `ocr_pipeline.json`，处理根为
> `材料处理/<年>/<地区>/`，源 PDF 在 `Docx/<年>/<年_地区>.pdf`；
> `images` 阶段调用 `tools/pdf_extract_images.py` 无损提取内嵌图。批量用
> `make material-batch ARGS="--auto-serve"` 或
> `make ocr-batch ARGS="--only 2026/湖北"`。下文示例中的 `课程材料处理`、
> `课程基础材料` 等路径为 Teach_Assess 原项目示例，按本项目替换即可。

> 工具入口：`python3 -m tools.ocr_pipeline ...`（唯一入口）
> 单元测试：`python3 -m unittest tools.test_ocr_pipeline` 或 `make tools-test`

---

## 一、结论：OvisOCR3 能否返回版面信息？

**能，而且这是 OvisOCR3 相对 OvisOCR2 的关键升级。**

| 能力 | OvisOCR2 | OvisOCR3 |
| :--- | :--- | :--- |
| Markdown 正文 | 支持 | 支持 |
| 图片引用 | 仅在 Markdown 中给 `<img src="images/bbox_l_t_r_b.jpg">` 图片框 | 支持；同时可用 structured/layout 模式返回 |
| 元素类别（正文/标题/公式/表格/图片/页眉…） | **不返回** | **返回**：`category` |
| 每个元素的 bbox | 只有图片框 | **所有元素**：`bbox=[x_min,y_min,x_max,y_max]` |
| 每个元素的文字内容 | 混在 Markdown 中 | **`content` 与 bbox 一一对应** |
| 纯版面检测 | 不支持 | `document_layout` 模式，只返回 bbox + category |
| 结构化 JSON | 不支持 | `document_structured` 模式 |
| 跨页表格 | 仅启发式 | `crosspage_table` 提示词 + 两页上下文重建 |
| 高清裁图依据 | 只能按图片标签裁 | **可按任意元素的 bbox 从原页高清裁剪** |

因此，本项目现在的取图逻辑是：

1. **文字版 PDF**：优先 `pdfimages -all` 从原 PDF 无损提取内嵌图（最高清、保原始编码）；
2. **扫描版 PDF / 纯矢量页 / 需要按版面块取图**：用 OvisOCR3 structured 或 PaddleOCR-VL `layout_det_res`
   的 bbox，按归一化坐标回到**原页渲染图**上裁剪，而不是使用 OCR 引擎自动生成的 Markdown 裁图；
3. 两引擎的 bbox 都是**源数据**，会原样保存在 `ovis/structured`、`ovis/layout`、`paddle/structured`，
   后续可随时换 DPI 重裁，无需重新跑模型。

> 坐标约定：OvisOCR3 与 PaddleOCR-VL 的归一化框均以页面左上角为原点；Ovis 为 `[0,1000)`，
> Paddle 先给页图像素框、程序再归一化。程序内部统一保存 `bbox`（0~1000）与 `pixel_bbox`（页图像素）。

---

## 二、与现有材料处理流程的关系

角色保持不变：

| 角色 | 引擎 | 输出 | 用途 |
| :--- | :--- | :--- | :--- |
| **底本** | **OvisOCR3**（`ovis` 阶段） | `ovis/output.md` + `ovis/raw`、`ovis/structured`、`ovis/layout` + `ovis/images` + `ovis/crops` | `merged.md` 正文底稿、版面源数据 |
| **验证** | **PaddleOCR-VL-1.6**（`paddle` 阶段） | `paddle/output.md` + `paddle/raw`、`paddle/structured` + `paddle/images` | 独立复认、带标签的版面框 |
| **旁证** | `pdftotext -layout` | `pdftotext.txt` | 文字版纯文本旁证 |
| **主数据源** | 人工交叉验证 | `merged.md` | 四件套 / 周练月考 / 补充材料只读此文件 |

`merged.md` 仍由 `tools/material_merge.py` 生成，仍以 Ovis 输出为底本；本程序只是把 OvisOCR2
替换为 OvisOCR3，并把每次识别的原始响应、结构化版面、页图尺寸、模型与提示词版本一起保留下来。

---

## 三、环境与模型

### 3.1 OvisOCR3

- **继续使用原 OvisOCR2 的 Python 环境**：Anaconda `ovis_ocr`，无需新建环境；
- 模型目录：`/home/shui/AI/ATH-MaaS/OvisOCR3`（与 `OvisOCR2` 同级）；
- 依赖：`vllm==0.22.1`、`pillow`、`pymupdf`（原环境已具备）；
- 默认 `enforce_eager=True`，跳过 CUDA Graph，加载约 1 分钟；批量运行时模型**只加载一次**。

可用环境变量覆盖模型路径：

```bash
export OVIS_MODEL=/home/shui/AI/ATH-MaaS/OvisOCR3
# 或 OCR_MODEL_PATH / OVIS_MODEL_PATH
```

### 3.2 PaddleOCR-VL

- 服务化，默认 `127.0.0.1:8203`；
- 启动 / 关闭：

```bash
./paddlex_serve_start.sh
./paddlex_serve_stop.sh
# 或
python3 -m tools.ocr_pipeline serve start
python3 -m tools.ocr_pipeline serve stop
python3 -m tools.ocr_pipeline serve status
```

- 也可以用 `--auto-serve` 让流水线在 Paddle 阶段自动启动、结束自动关闭；
- 服务单次请求有页数上限（当前约 50 页），程序会自动用 `qpdf` 分块（默认每块 20 页），
  不会出现“只识别了前 50 页但不知道”的静默截断。

> 两个引擎共用 GPU，**不要同时加载**。推荐顺序：Paddle 阶段（服务）→ 关闭服务 → Ovis 阶段（vLLM）。
> 流水线默认阶段顺序就是 `text → images → paddle → ovis → merge → check`。

---

## 四、目录与产物

以一份 PDF 的处理目录 `<处理目录>/` 为例：

```
<处理目录>/
├── .ocr_state.json          # 阶段/逐页/错误状态（断点续跑依据，原子写）
├── .ocr_lock                # 目录锁，防止两个进程同时写同一目录
├── source.json              # 源 PDF：路径、页数、sha256、文字版/扫描版、页尺寸
├── pdftotext.txt            # 旁证；扫描版写入占位行，避免空文件
├── pageimages/              # Ovis 推理用整页 PNG（默认 300 dpi）
│   ├── page_0001.png
│   └── .render.json         # 记录渲染 DPI，DPI 改变时自动重渲染
├── ovis/
│   ├── output.md            # 主 Markdown（含 front matter）
│   ├── images/              # Markdown 图片标签对应的裁图（JPEG，旁证）
│   ├── pages/page_0001.md   # 每页 Markdown
│   ├── raw/page_0001.json   # 原始响应 + 提示词 + finish_reason + 页图尺寸
│   ├── structured/page_0001.json  # 规范化 blocks：bbox/category/content/pixel_bbox
│   ├── layout/page_0001.json      # 纯版面：bbox/category
│   ├── crops/page_0001/           # 按视觉块 bbox 从原页裁出的 PNG（默认 300 dpi）
│   ├── crops/manifest.json  # 视觉块裁图清单（页码/bbox/类别/文件）
│   └── manifest.json        # 模型、提示词模式、页状态、产物清单
├── paddle/
│   ├── output.md            # 验证引擎 Markdown
│   ├── images/              # 服务返回的图片（按页加 pNNNN_ 前缀，避免重名）
│   ├── pages/page_0001.md
│   ├── raw/page_0001.json   # 每页 prunedResult + Markdown + 图片映射（figsize 可读）
│   ├── structured/page_0001.json  # 规范化版面框 + 标签 + 内容
│   ├── restructured/chunk_0001_0020.md  # 可选：块内跨页重构结果
│   └── manifest.json
├── pageimages_crop_300/     # 可选：structured 裁图专用整页渲染（crop_dpi 与 dpi 不同时）
├── pdfimages/               # 原 PDF 内嵌图无损提取（沿用 pdf_extract_images.py）
├── merged.md                # 最终主数据源
└── ocr_crops_600/           # 可选：用 crops 子命令按已存 bbox 高清重裁
    ├── pageimages_600/
    └── manifest.json
```

### 关键源数据字段

`ovis/structured/page_NNNN.json`：

```json
{
  "schema_version": 1,
  "page": 1,
  "source_sha256": "…",
  "width": 2480,
  "height": 3508,
  "render_dpi": 300,
  "blocks": [
    {
      "index": 0,
      "bbox": [65, 390, 433, 772],
      "pixel_bbox": [161, 1368, 1073, 2708],
      "category": "image",
      "content": "<img src=\"images/bbox_65_390_433_772.jpg\" />",
      "page": 1
    }
  ],
  "markdown_crops": [{"bbox": [65, 390, 433, 772], "image": "images/page_1_bbox_65_390_433_772.jpg"}],
  "block_crops": [{"bbox": [65, 390, 433, 772], "category": "image", "image": "page_0001/000_image.png"}],
  "diagnostics": {"json_complete": true, "schema_issues": [], "valid": true}
}
```

- `bbox`：`[x_min,y_min,x_max,y_max]`，`0~1000`，相对**送入模型的那一页图**，原点左上；
- `pixel_bbox`：同一框在 `width × height` 页图上的像素坐标，便于人工核对；
- `content`：该元素被识别出的原始文字/LaTeX/HTML 表格/图片标签；
- `diagnostics`：JSON 是否完整、类别是否合法、是否有截断尾部；**原始响应始终保留在 `raw/`**。

`paddle/raw/page_NNNN.json` 保留服务返回的 `prunedResult`（含 `layout_det_res.boxes`、
`parsing_res_list`、`width/height`），`paddle/structured/page_NNNN.json` 是程序整理后的统一格式。

---

## 五、快速开始

### 5.1 单份 PDF（推荐）

```bash
# 仅 OvisOCR3 底本（模型加载一次，自动断点续跑）
/home/shui/.conda/envs/ovis_ocr/bin/python -m tools.ocr_pipeline run \
    -i "课程基础材料/…/xxx.pdf" \
    -o "课程材料处理/…/xxx" \
    --stages ovis

# 全流程（Paddle 服务自动启停；含 Ovis，须用 ovis_ocr 环境）
/home/shui/.conda/envs/ovis_ocr/bin/python -m tools.ocr_pipeline run \
    -i "课程基础材料/…/xxx.pdf" \
    -o "课程材料处理/…/xxx" \
    --auto-serve

# 只重跑 Paddle 阶段
python3 -m tools.ocr_pipeline run -i "…/xxx.pdf" -o "…/xxx" \
    --stages paddle --auto-serve --force-stage paddle
```

### 5.2 批量（几十份、长时间）

```bash
# 1) 先看将处理哪些目录（不加载模型、不占 GPU）
python3 -m tools.ocr_pipeline plan --root 课程材料处理 --root 周练月考材料处理 --root 补充材料处理

# 2) 统计完成情况；旧 OvisOCR2 目录会标记 [需升级]
python3 -m tools.ocr_pipeline status --root 课程材料处理 --root 周练月考材料处理 --root 补充材料处理

# 3) 批量升级/识别（Paddle 自动启停，Ovis 模型只加载一次；须用 ovis_ocr 环境）
nohup /home/shui/.conda/envs/ovis_ocr/bin/python -m tools.ocr_pipeline batch \
    --root 课程材料处理 --root 周练月考材料处理 --root 补充材料处理 \
    --auto-serve --force-stage ovis \
    > /tmp/opencode/ocr_batch.out 2>&1 &

# 4) 断点续跑：直接重复上面的命令即可；已完成的页/块会自动跳过

# 旧目录没有 paddle/raw 时，全阶段批量会补跑 Paddle 以保留版面源数据；
# 若只想先升级 Ovis 底本、暂时不动 Paddle：
/home/shui/.conda/envs/ovis_ocr/bin/python -m tools.ocr_pipeline batch \
    --root 课程材料处理 --root 周练月考材料处理 --root 补充材料处理 \
    --stages ovis,merge,check --force-stage ovis
```

> `--root` 可以是处理根目录（如 `课程材料处理`），也可以是单个处理目录；
> 程序会从 `ovis/output.md` 的 `source:` 字段或 `source.json` 自动定位源 PDF。
> 旧目录没有 `source.json` 也能定位。

### 5.3 显式作业清单

```bash
# 文本清单：每行 PDF<TAB>处理目录
python3 -m tools.ocr_pipeline batch --jobs-file jobs.tsv --auto-serve

# JSON：{"jobs": [{"pdf": "...", "output": "..."}]}
python3 -m tools.ocr_pipeline batch --jobs-file jobs.json

# 单个显式作业
python3 -m tools.ocr_pipeline batch \
    --pair "课程基础材料/…/a.pdf::课程材料处理/…/a" \
    --auto-serve
```

### 5.4 配置文件（可选）

```json
{
  "model": {"path": "/home/shui/AI/ATH-MaaS/OvisOCR3", "gpu_memory_utilization": 0.8},
  "pdf": {"dpi": 300, "text_min_chars": 40},
  "ovis": {"prompt_mode": "structured", "batch_size": 1, "crop_dpi": 300, "crop_format": "png"},
  "paddle": {"host": "127.0.0.1", "port": 8203, "page_chunk": 20, "auto_serve": false},
  "pipeline": {"stages": ["text", "images", "paddle", "ovis", "merge", "check"], "lock": true}
}
```

```bash
/home/shui/.conda/envs/ovis_ocr/bin/python -m tools.ocr_pipeline batch \
    -c ocr_pipeline.json --root 课程材料处理 --auto-serve
```

命令行参数优先级高于配置文件；环境变量 `OVIS_MODEL`、`PADDLE_HOST`、`PADDLE_PORT`、
`OCR_TMPDIR` 也会覆盖默认值。

---

## 六、分阶段说明

| 阶段 | 作用 | 是否需要 GPU | 完成判断 |
| :--- | :--- | :--- | :--- |
| `text` | 探测 PDF 页数/文字版/扫描版；`pdftotext -layout` | 否 | `pdftotext.txt` 非空 + `source.json` |
| `images` | `pdf_extract_images.py` 无损提取内嵌图到 `pdfimages/` | 否 | `pdfimages/manifest.json` |
| `paddle` | 分块调用 PaddleOCR-VL，保存 raw/structured/Markdown | 是（服务） | 每页 `paddle/raw/page_N.json` |
| `ovis` | OvisOCR3 structured/markdown + 版面源数据 + 裁图 | 是（vLLM） | 每页 `ovis/raw/page_N.json` |
| `merge` | `tools/material_merge.py` 生成 `merged.md` | 否 | `merged.md` |
| `check` | `tools/check_material.py` 校验四要素与逐页源数据 | 否 | 退出码 0 |

阶段可任意组合：`--stages text,ovis`、`--stages paddle`、`--stages merge,check` 等。
程序会按 `text → images → paddle → ovis → merge → check` 的规范顺序执行，避免 Paddle 与 Ovis
同时占用显存；未知阶段会直接报错。

### 6.1 Ovis 输出模式

`--ovis-mode`：

- `structured`（默认）：一次调用同时得到文字 + bbox/category/content，性价比最高；
- `markdown`：纯 Markdown，只有图片 bbox，无元素类别标签；
- `both`：分别调用 Markdown 与 structured，成本约翻倍，适合关键材料做双重检查；
- `layout`：只做版面检测，不识别文字，一般用于单独补版面数据。

### 6.2 图片裁剪

- `ovis/images/`：Markdown 图片标签对应的裁图，供人工对照；
- `ovis/crops/`：按 structured **所有视觉类别**（`image/chart/table/header_image/footer_image/seal`）
  从原页裁剪，默认 PNG、默认 `crop_dpi=300`；
- 需要更高清时**不必重跑 OCR**：

```bash
python3 -m tools.ocr_pipeline crops \
    -d "课程材料处理/…/xxx" \
    --dpi 600 \
    --out "课程材料处理/…/xxx/ocr_crops_600"
```

  `crops` 只读取已保存的 `ovis/structured`，重新渲染原 PDF 页面并裁剪，输出 `manifest.json`
  （含 source、sha256、bbox、pixel_bbox、类别、输出文件）。

> 制作配图时仍以 `pdfimages/`（文字版内嵌原图）为第一优先；`ovis/crops` 用于扫描版、
> 纯矢量页、或多子图/版面块需要按 bbox 定位的场景。不要直接把 OCR 自动裁图当成品。

---

## 七、断点续跑与异常处理

### 7.1 断点粒度

- **Ovis**：逐页保存 `raw/structured/layout/pages`；每页成功后立即更新 `.ocr_state.json`。
  中断后重跑，已完成的页直接跳过，不重新推理。若 JSON 不完整、类别异常或
  `finish_reason=length`，该页标为 `partial`，正文仍保留但下次运行会重试。
- **Paddle**：按 chunk（默认 20 页）保存每页 raw；chunk 有哈希（源 PDF + 选项 + 页范围），
  已完成 chunk 直接跳过；中断只会重做当前 chunk。
- **text/images/merge/check**：单文件/单目录产物存在且非空即跳过；`--force` 重做。

### 7.2 源文件变化

`source.json`、Ovis raw、Paddle raw 都记录源 PDF 的 `sha256`。若源 PDF 被替换：

- Ovis 会检测到 hash 变化，自动重渲染页图并重跑；
- Paddle chunk 哈希变化，自动重跑；
- `merged.md` 的 `source_sha256` 由 `material_merge.py` 校验，漂移会报错，需 `--force` 重建。

### 7.3 卡死、断连、超时

- **Ovis**：每次 `generate` 用 `SIGALRM` 限制 `--page-timeout`（默认 600s）；超时记为该页失败，
  继续下一页；若整批卡死无法中断，外层用 `timeout` 兜底：

```bash
timeout 12h /home/shui/.conda/envs/ovis_ocr/bin/python -m tools.ocr_pipeline batch \
    --root 课程材料处理 --auto-serve
```

  被 `timeout` 杀掉后直接重跑同一命令即可续跑。

- **Paddle**：请求超时/连接断开自动指数退避重试（默认 3 次）；`--auto-serve` 下若仍失败，
  会尝试重启服务再重试当前 chunk。若 `paddle/manifest.json` 的 `restructure_errors` 非空，
  说明块内跨页重构未完成，用 `--force-stage paddle` 重跑该阶段。
- **服务页数上限**：程序按 `--paddle-page-chunk` 用 `qpdf` 分块，默认 20 页，远低于 50 页上限；
  返回页数不符会立即报错，不会静默丢页。
- **目录锁**：每个处理目录有 `.ocr_lock`；两个进程同时写同一目录时，后来者跳过并记录，
  避免状态互相覆盖。
- **失败隔离**：默认一个作业失败不影响后续作业；`--fail-fast` 才会立即停止。

### 7.4 日志与报告

- 批次日志：默认 `/tmp/opencode/ocr/logs/batch_<时间>.log`（可用 `--log-file` 或配置 `logging.dir` 覆盖）
- 批次报告：同目录 `batch_<时间>.json`（逐作业、逐阶段状态，失败作业列表）
- 单目录状态：`<处理目录>/.ocr_state.json`（阶段、逐页、最近 200 条错误）

长时间运行建议：

```bash
nohup /home/shui/.conda/envs/ovis_ocr/bin/python -m tools.ocr_pipeline batch ... > /tmp/opencode/ocr_batch.out 2>&1 &
tail -f /tmp/opencode/ocr_batch.out
```

---

## 八、大批量运行建议

1. **先 `plan` 和 `status`**，确认作业数量、源 PDF 是否都能定位、哪些目录还是 OvisOCR2；
2. **先小批量试跑**：`--limit 2` 或 `--only 关键词`，检查图片/版面/公式质量；
3. **Paddle 与 Ovis 分阶段**跑，避免两个模型同时占显存；
4. Ovis 模型在一个 batch 进程内只加载一次；不要为每份 PDF 单独启动进程；
5. 扫描版 PDF 可把 `--dpi` 提到 400（更清晰但更慢），成品裁图用 `crops --dpi 600`；
6. 磁盘：页图 + 裁图 + raw 会占空间，建议处理目录所在磁盘预留足够空间；
7. 处理完成后跑 `make check-material` 与 `make check-fig-sources` / `make check-figsize`。

---

## 九、PDF 类型与取图策略

| PDF 类型 | 识别 | 取图 |
| :--- | :--- | :--- |
| 文字版（WPS/Word 导出，含内嵌位图） | Ovis + Paddle + pdftotext | **`pdfimages -all` 无损提取**；多子图用 `recrop_figures.py` |
| 扫描版（整页一张位图） | Ovis + Paddle；pdftotext 仅占位 | 整页渲染后按 Ovis structured / Paddle layout 的 bbox 裁；`crops --dpi 600` |
| 纯矢量页（`pdfimages -list` 为 0） | 同上 | `splitpicture pdfsplit --pdf-mode vector` 或 `crops` 后按需处理；禁止用 `pdftoppm` 直接当成品 |
| 多栏/复杂版面 | Ovis structured + Paddle layout 互证 | 按 bbox 裁，标签以 Paddle `layout_det_res` 为主、Ovis 补充 |
| 跨页表格 | Ovis structured/markdown；Paddle 块内重构 | 先按页保存，跨页以 `merged.md` 人工/规则合并为准 |

---

## 十、跨项目复用（迁移到其它两个项目）

本程序只依赖 Python 标准库 + `pymupdf` + `Pillow` + `requests`（Paddle）+ `vllm`（Ovis），
不依赖 Teach_Assess 的 LaTeX/材料目录结构。复用方式：

1. 复制整个 `tools/ocr_pipeline/` 到目标项目同名位置；
2. 目标项目若有自己的 `tools/material_merge.py`、`tools/pdf_extract_images.py`、
   `tools/check_material.py`，无需修改；程序会按相对路径自动调用；
4. 用环境变量适配路径：

```bash
export OVIS_MODEL=/home/shui/AI/ATH-MaaS/OvisOCR3
export PADDLE_HOST=127.0.0.1
export PADDLE_PORT=8203
export OCR_TMPDIR=/tmp/opencode
```

5. 作业来源可用三种方式：
   - `--root <处理根目录>`：适用于已有 `ovis/output.md` 的目录（自动定位源 PDF）；
   - `--source-root <源根> --output-root <输出根>`：按相对目录镜像新建作业；
   - `--jobs-file` / `--pair`：完全显式，适合各项目自己的命名规则。

> 迁移前先在 Teach_Assess 验证；确认后只需同步 `tools/ocr_pipeline/`，
> 目标项目的材料规范/目录规则仍由各自项目维护。

---

## 十一、测试与验收

```bash
# 单元测试（不占 GPU）
python3 -m unittest tools.test_ocr_pipeline -v
# 或
make tools-test

# 预览配置/计划（不占 GPU）
python3 -m tools.ocr_pipeline plan --root 课程材料处理 --limit 3
python3 -m tools.ocr_pipeline status --root 课程材料处理 --limit 3

# 单页模型烟测（占 GPU；模型路径存在时）
/home/shui/.conda/envs/ovis_ocr/bin/python -m tools.ocr_pipeline run \
    -i /tmp/opencode/ocr_smoke/smoke.pdf -o /tmp/opencode/ocr_smoke/out \
    --stages ovis --dpi 150
```

验收标准：

- `ovis/raw/page_*.json`、`ovis/structured/page_*.json`、`ovis/layout/page_*.json` 齐全；
- `paddle/raw/page_*.json` 含 `prunedResult.layout_det_res.boxes` 与 `parsing_res_list`；
- `ovis/crops/` 或 `ocr_crops_600/` 的每张图都能在 `manifest.json` 中追溯到页码与 bbox；
- 中断后重跑不重复推理已完成页；`status` 能显示进度；
- `make check-material` 四要素完整、图片引用有效、底稿未漂移；新版 `ovis/manifest.json`、
  `paddle/manifest.json` 存在时，逐页 `raw/structured/layout/pages` 源数据必须齐全，
  且 manifest 状态必须为 `complete`（`partial` 视为未完成）。

---

## 十二、参数速查

### `run` / `batch`

| 参数 | 说明 |
| :--- | :--- |
| `-i/--input`、`-o/--output` | 单份 PDF 与处理目录（`run` 必填） |
| `--root` | 处理根目录，可重复；自动从 `source.json`/`ovis/output.md` 定位源 PDF |
| `--jobs-file` | JSON/TSV 作业清单（`pdf<TAB>out`） |
| `--pair PDF::OUT` | 显式作业，可重复 |
| `--source-root` / `--output-root` | 按相对目录镜像新建作业 |
| `--stages` | 逗号分隔阶段；程序会按 `text→images→paddle→ovis→merge→check` 规范顺序执行 |
| `--force` / `--force-stage` | 全部 / 指定阶段重跑 |
| `--auto-serve` | Paddle 阶段需要时自动启动服务，结束后关闭 |
| `--dpi` / `--crop-dpi` | 推理页图 DPI / 视觉块裁图 DPI |
| `--ovis-mode` | `structured`（默认）/ `markdown` / `both` / `layout` |
| `--ovis-batch-size` | Ovis 批量推理页数（默认 1，断点粒度最细） |
| `--page-timeout` | 单页/单批推理超时秒数（默认 600） |
| `--paddle-page-chunk` | Paddle 单次请求页数（默认 20，低于服务 50 页上限） |
| `--no-paddle-restructure` | 关闭 Paddle 块内跨页重构 |
| `--no-block-crops` | 不保存 Ovis structured 视觉块裁图 |
| `--dry-run` | 只列计划，不加载模型、不占 GPU |
| `--fail-fast` | 首个错误后停止后续作业（默认继续其它作业） |
| `--limit` / `--only` | 限制作业数量 / 仅路径含关键词者 |

### `status` / `plan`

`status` 显示页数、文字/内嵌图、Ovis/Paddle 状态、合并状态与是否需升级；
`--json` 输出结构化结果。`plan` 只列作业与阶段，不执行。

### `crops`

| 参数 | 说明 |
| :--- | :--- |
| `-d/--dir` | 处理目录（必须已有 `ovis/structured`） |
| `--pdf` | 源 PDF；缺省自动定位 |
| `--dpi` | 重裁渲染 DPI（默认 300） |
| `--format` | `png` / `jpg` |
| `--category` | 只裁指定类别，可重复 |
| `--out` | 输出目录（默认 `<处理目录>/ocr_crops_<dpi>`） |

### `serve`

`serve start|stop|status`：启停/查看 PaddleOCR-VL 服务；服务脚本默认取项目根
`paddlex_serve_start.sh` / `paddlex_serve_stop.sh`，可在配置中覆盖。

---

## 十三、常见问题

**Q1：为什么 Ovis 的 `block_crops` 像素框和 `blocks.pixel_bbox` 不一样？**
A：`blocks.pixel_bbox` 是相对推理页图（`pageimages/`，默认 300 dpi）；`block_crops` 可能来自
`pageimages_crop_600/`（裁图 DPI），两者是同一归一化 bbox 在不同 DPI 下的像素坐标，均正确。

**Q2：`ovis/images/` 还是自动裁图，能用于成品吗？**
A：`ovis/images/` 是 Markdown 内图片引用的落盘裁图，仅作校勘与人工对照；成品配图优先
`pdfimages/`，扫描版用 `ovis/crops/` 或 `crops --dpi 600` 的高清裁图，并按项目规范登记来源。

**Q3：Paddle 只识别了前几十页？**
A：检查 `paddle/manifest.json` 的 `pages` 与 `page_status`；程序默认分块 20 页，不会超过服务上限。
若仍缺页，`--force-stage paddle` 重跑，并查看日志中的“返回页数不符”提示。

**Q4：能否只用 OvisOCR3 的 layout 模式？**
A：可以：`--ovis-mode layout --stages ovis`。它只产出 `layout/`，不产出正文，适合单独补版面数据。

**Q5：旧 OvisOCR2 目录如何升级？**
A：直接运行 `python3 -m tools.ocr_pipeline batch --root <处理根> --stages ovis,merge,check --force-stage ovis`；
程序会按新格式重写 `ovis/` 并重建 `merged.md`。如需保留旧结果，先把处理目录复制到新位置。
