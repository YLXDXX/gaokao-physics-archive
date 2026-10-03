# splitpicture 使用说明（高考物理真题库）

> 外部工具 **splitpicture**（源码见 gitee：
> <https://gitee.com/ylxdxx/splitpicture>）用于**图像切分、去白边、填白、
> 智能检测图形/子图/标签**。本项目用它把**从 PDF 无损提取的内嵌图**按子图裁剪、
> 去标签，回填各卷 `figs/`（见 `材料处理与OCR规范.md` 第五节、
> `高考物理真题制作规范.md` 第五节）。
>
> **日常制卷优先走本项目封装** `tools/recrop_figures.py`（recipe 驱动 + `crop_compare/`
> 对比图 + `check_recrop.py` 校验）；本文同时给出**直接调用 CLI / GUI** 的用法，
> 用于分诊、复核与疑难图人工处理。

---

## 一、环境与自检

```bash
which splitpicture            # 需在 PATH；也可用 SPLITPICTURE=/path/to/splitpicture 指定
splitpicture --version        # 本项目要求 ≥ 0.4
splitpicture --capabilities   # JSON：version / ocr / opencv / features
```

本项目当前环境：**splitpicture 0.4.1**，`ocr=true`（tesseract 可用），
features 含 `panels`、`options`、`erase-labels`、`labels-file`、`rects-file`、
`json-items`、`tight`、`rects-base` 等。

- **≥ 0.4 的原因**：`recrop_figures.py preview` 依赖 `detect --preview` 的外部框叠加；
  `apply` 依赖 `split --json` 的 `items`（rect → output → skipped 的无歧义映射）。
- 无图形环境（脚本/CI）时设置 `QT_QPA_PLATFORM=offscreen`；`recrop_figures.py`
  与 `match_figures.py` 已自动设置。
- 环境变量 `SPLITPICTURE` 可覆盖可执行文件路径（两个封装脚本均读取）。
- OCR 依赖 `tesseract` + `chi_sim`/`eng`；未装时自动退化为纯几何，仍可用于
  `--panels/--options`（其标签判定以几何为主）。

---

## 二、三种检测模式：先选对模式

splitpicture 的“自动识别区域”有三套并列算法，**选错模式会切错**。判据如下：

| 模式 | 适用排版 | 本项目典型场景 |
| :--- | :--- | :--- |
| 默认 `--detect` | 通用图形检测；把图内分离的文字/符号/公式**并入主图**，剔除子图标签 | 单幅示意图；坐标图；元素多的复合图整体 |
| `--options` | **选项图在上、`A/B/C/D` 标签在下**（每个选项一列） | 选择题的“四图选项”（`\fourchoices[ispicture=true]`） |
| `--panels` | **多子图带标签行**：`图甲/图1/图a/A-D/甲乙丙丁`，横排或 2×2 | 一道题多幅配图（`\twopicture…\ninepicture`） |

选择顺序建议：

1. 一道题里**并列多幅子图**（图 `(a)(b)`、`图1 图2`、`甲乙丙`）→ `--panels`；
2. 四个**图片选项**、字母 A/B/C/D 在每张图下方 → `--options`；
3. **单幅**图 / 图内标注与主图分离较多 → 默认 `--detect`；
4. 以上都不理想、且要严格按框裁剪 → 回退 `-r x,y,w,h` 手绘 或 GUI 框选。

相关参数：`--gutter`（子图间最小空白带）、`--min-area`（最小内容面积）、
`--text-gap`（同图元素聚合间隔）、`--no-ocr`（纯几何）。

> **实战教训（本项目真实数据）**
> - `广东 p3_3.jpg` 是**同一幅图的两子图 `(a)(b)`**，用 `--options` 会多切出一个
>   细小碎块（把 `(b)` 图题区域当成一个“选项列”）；这类应改用 `--panels`。
> - `广东 p7_11.jpg` 用 `--panels` 得到正确的 `(a)(b)` 两块，但**居中的图题“图1”
>   （横跨两子图中缝）未被判为标签**，`--erase-labels` 后仍残留在左块右下角。
>   凡“图题居中、介于两子图之间”的排版，**必须**在 `crop_compare/` 核对，必要时
>   用手工 `erase` 框补擦。
> - `广东 p8_13.jpg` 用 `--panels` 检出两框但**相互侵入**（右框左伸），`--tight`
>   可沿重叠区中线收缩（`453→417`、`570→534`），但 `--tight` **只收缩、可能切掉
>   边缘内容**，仅用于分诊/预览，**不得作为最终实裁框**。

---

## 三、标签检测与擦除（`labels` / `--erase-labels`）

多子图标签通常在图下方，裁剪时避开即可。两类**难例**必须“擦除”而非“裁剪”：

1. 标签与图内文字**同高**（如“丙”与“电源”同一行）；
2. 标签落在**宽大底边**下方附近，矩形边界难以兼顾。

能力：

- `detect` 额外输出**标签框** `labels`（`kind` = `label|caption|annotation|unknown`）；
  `--save-labels [file]` 可单独存为矩形数组；预览图**红框=图形、蓝框=标签**。
- `split --erase-labels`：**先擦白标签再裁剪**——一步得到完整子图。
- `fill --labels-file <labels.json>` / `fill --erase-labels`：只擦白、不检测图形。
- 几何“底部单字标签”`--bottom-labels`（`--panels`/`--erase-labels` 隐式开启），
  可识别 OCR 常读错的 `甲/乙/丙/丁`；`--options` 用自身规则处理 A/B/C/D。
- `--labels-file` 与 `--rects-file` **同格式**（`{x,y,w,h}` / `{x0,y0,x1,y1}` /
  `[x0,y0,x1,y1]`），且**严格校验**：缺键/非数值会报错，不再退化为全 0 矩形。

两种工作流：

```bash
# 一步法：检测 + 擦标签 + 裁剪（严格无损请加 -f png）
splitpicture split -i p7_18.png --panels --erase-labels -f png -d out -p fig

# 两步法：先出标签框，人工复核/编辑后再擦、再裁
splitpicture detect -i p7_18.png --panels --save-rects rects.json --save-labels labels.json --preview prev.png
splitpicture fill   -i p7_18.png --labels-file labels.json -o p7_18_clean.png
splitpicture split  -i p7_18_clean.png --panels -d out -p fig
```

> **标签检测的保守性**：单个汉字标签主要靠几何法（下半部、横向孤立、正上方有图、
> 正下方无墨迹）；无边框坐标图的刻度数字与“子图标签”形态相似，**单幅坐标图**请用
> 默认 `detect` 或加 `--no-bottom-labels`。检测是启发式，**务必 `--preview` 复核**。

---

## 四、本项目封装：`tools/recrop_figures.py`（推荐流程）

把“从内嵌图裁子图 → 回填 `figs/` → 生成裁剪前后对比图”固化为 **recipe 驱动**的
可复现流程，所有 splitpicture 调用都由它完成。

```bash
# 1) 分诊：批量生成候选框预览，列出多子图（≥2）与标签数
python3 tools/recrop_figures.py scan 材料处理/2026/广东/pdfimages
#    → 写出 材料处理/.../pdfimages/review/<名>/{rects.json,labels.json,preview.png}
#    追加 --recipe-out out.json 可为多子图候选生成 .recrop.json 草稿（target 为占位名，
#    需人工改成 figs/<题号><子图字母>.png 并逐张核对后 apply）：
python3 tools/recrop_figures.py scan 材料处理/.../pdfimages --recipe-out /tmp/draft.json

# 2) 预览单张候选框（人工核对 rect）
python3 tools/recrop_figures.py split 材料处理/2026/广东/pdfimages/p7_11.jpg -o preview.png

# 2b) 查看/导出某图的图形框与标签框（辅助写 recipe）
python3 tools/recrop_figures.py labels 材料处理/.../p7_11.jpg --mode panels -o labels.json --preview prev.png

# 3) 写 recipe：登记 source 与 crops(rect→target)，可选 erase / erase_labels / trim
#    文件：试卷/<年>/<地区>/.recrop.json

# 4) 只读叠加预览：绿=实裁框、黄=擦除框（apply 前核对）
python3 tools/recrop_figures.py preview 试卷/2026/四川/.recrop.json

# 5) 裁剪回填 figs/ 并生成 crop_compare/<文档>_裁剪前后.png
python3 tools/recrop_figures.py apply 试卷/2026/四川/.recrop.json

# 6) 校验 recipe 与 figs/ 结构/尺寸/文件头一致
python3 tools/check_recrop.py
```

recipe 格式（路径相对项目根）：

```json
{
  "entries": [
    {
      "source": "材料处理/2026/四川/pdfimages/p7_6.jpg",
      "crops": [
        {"rect": [0, 0, 900, 608],   "target": "试卷/2026/四川/figs/11a.png"},
        {"rect": [900, 0, 744, 608], "target": "试卷/2026/四川/figs/11b.png"}
      ],
      "erase": [[x, y, w, h]],
      "erase_labels": "panels",
      "trim": {"padding": 8, "threshold": 200}
    }
  ]
}
```

- `crops[].rect`：源图坐标 `[x,y,w,h]`；`target` 为目标 `figs/` 路径（**这是“裁剪到落位”的唯一权威**）。
- `erase`：**手工**擦除框（用于 splitpicture 漏检的标签，如居中“图1”）；
  `erase_labels`：`"panels"`（默认）/ `"options"` / `"default"`，交 splitpicture **自动检测标签**后擦除。
  二者合并为一份 `labels.json`，在裁剪前**原生擦除**（源文件不动）。
- `trim`：裁剪后 `--trim` 去白边（`padding` 留白像素、`threshold` 判白阈值）；
  开启后 target 尺寸会小于 `rect`。
- `compare`：可显式 `true/false`；默认“多块 / 有擦除 / 单块但切掉了非空白”才生成对比图。
- **必须逐张打开 `crop_compare/<文档>_裁剪前后.png`**（左=原图，红框=擦除区；右=回填子图）。

> 用 recipe 的好处：可复查（`preview` 绿/黄框）、可回喂（编辑 `rects/labels` 再 `apply`）、
> 可校验（`check_recrop`）。**新卷应尽量用 recipe**，避免“手工 PIL 直接裁”留下不可复现的图。

---

## 五、直接调用 splitpicture CLI（分诊 / 单张处理）

```bash
# 候选框预览（红=图形、蓝=标签）
splitpicture detect -i in.jpg --panels  --preview prev.png
splitpicture detect -i in.jpg --options --preview prev.png
splitpicture detect -i in.jpg --detect  --preview prev.png     # 默认模式（--detect 可省）

# 导出框，供人工编辑后重放
splitpicture detect -i in.jpg --panels --save-rects rects.json --save-labels labels.json

# 按矩形裁剪（-f png 为严格无损；JPEG 会按估计质量重编码）
splitpicture split -i in.jpg --rects-file rects.json -f png -d out -p page11

# 一步：检测+擦标签+裁剪
splitpicture split -i in.jpg --panels --erase-labels -f png -d out -p page11

# 只擦标签（不裁）
splitpicture fill -i in.jpg --panels --erase-labels -o in_clean.png

# JSON 便于脚本：split 额外给 items（rect→output→skipped/ok）；detect 额外给 labels
splitpicture split -i in.jpg --rects-file rects.json -d out -p x --json
splitpicture detect -i in.jpg --panels --json

# 只计划不写盘（split 会按 --trim 预判真实 skipped）
splitpicture split -i in.jpg --rects-file rects.json -d out -p x --dry-run

# 批量：整目录、4 路并行、每个输入单独子目录
splitpicture split --input-dir pages/ --panels --jobs 4 --per-file-subdir -d out -p q
```

- **输出路径**：`split --rects-file` 支持每个矩形写 `output` 字段，让 JSON 直接当“裁剪清单”。
- **无损**：`split/fill` 输出 JPEG 会重编码；**严格无损用 `-f png`**（线稿 PNG 常比 JPEG 更小）。
- **`--tight`**：只收缩相互侵入的检测框，供分诊/预览；**勿作最终实裁框**。

### GUI（疑难图人工框选）

```bash
splitpicture -i page.png --panels     # 打开界面并自动标框，随后可拖动/缩放
splitpicture -i page.png --options
splitpicture -i page.png              # 空白画布，右键加载图片
```

- 左键拖动画框、拖动移动/缩放；右键菜单可**去白边 / 填白 / 删框 / 导出/导入矩形(JSON)**；
  滚轮缩放、中键平移；导出 JSON 后可交命令行 `--rects-file` 批量重放。
- **推荐闭环**：`detect` 自动标框 → GUI 微调 → 导出 `rects.json` → `split --rects-file`。

---

## 六、高考物理图常见难例与调参

| 难例 | 现象 | 处理 |
| :--- | :--- | :--- |
| 无边框坐标图 | `--panels` 把刻度数字当标签擦掉 | 用默认 `--detect`，或加 `--no-bottom-labels` |
| 标签与图内文字同高 | 裁剪框删不净标签 | `--erase-labels`，或手工 `erase` + `--labels-file` |
| 图题居中（跨子图中缝） | “图1”残留在某子图角落 | 在 recipe 里补 `erase` 框，`crop_compare` 核对 |
| 2×2 子图 | 只横向切、漏行 | `--panels` 支持 2×2（按标签行高度分幅） |
| 选项图在上、A–D 在下 | 选项字母被裁进图 | `--options`；字母偏大时配 `--option-label-pattern` |
| 内部有间隙的示意图 | 被切成多块碎片 | 用 `--options`（列内再分行），或默认 `detect` 的合并；调大 `--text-gap` |
| 密集网格/装饰长条 | 检出多余小块 | 提高 `--min-area`、增大 `--gutter`，或 `--no-split-subfigures` |
| 相邻检测框相互侵入 | 多裁/重复 | `--preview` 复核；`--tight` 仅预览收缩，最终按内容人工取框 |
| 扫描件倾斜/噪点 | 检测不稳 | 本工具不做去斜/去噪；先外部纠正或改用人工框选 |
| 严格无损 | JPEG 重编码代损 | `split/fill` 加 `-f png` |

---

## 七、质量核对清单（每次裁剪都过一遍）

- [ ] 先用 `--preview` 看**红框=图形、蓝框=标签**是否合理（`recrop_figures.py preview` 另叠绿/黄框）。
- [ ] `apply` 后用 `crop_compare/<文档>_裁剪前后.png` **逐行**核对：无多裁、少裁、残留标签/图题。
- [ ] 子图**不得自带** `甲/乙/丙`、`A/B/C/D` 编号（编号由 `ChoiceQuestion` 自动生成）。
- [ ] `make check` 含 `check_recrop.py`，保证 recipe 与 `figs/` 结构一致。
- [ ] 只用原图，**严禁用 TikZ 重绘**（`材料处理与OCR规范.md` 第五节 4）。

---

## 八、与规范文档的关系

- 图片来源与复合图拆分总则：`材料处理与OCR规范.md` 第五节；
- 命名（题号+子图字母）、引用标签、去标签：`高考物理真题制作规范.md` 第五节；
- 脚本索引：`tools/README.md` 第三节（多子图裁剪）。
