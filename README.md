# gaokao-physics-archive

高考物理真题 · LaTeX 档案库。

收集各年份、各地区的高考物理真题，按**统一版式与规范**制作成一份份**可独立编译**的
LaTeX 文档，并为每道题保留**元数据**与**详解**，为后续高质量高考真题库建设提供数据基础。

> 本项目借鉴同机项目 `Teach_Assess`（黄香高中备课与测评项目）的经验：
> **去中心化**（每份卷独立目录、独立 `Makefile`、独立图片）、公共样式只在根目录一份、
> 材料处理采用**双 OCR 引擎 + pdftotext 交叉验证**、题目统一以 `ChoiceQuestion.sty`
> 的图片命令与答案/解析命令排版。

---

## 一、目录结构

```
项目根目录/
├── 试卷/<年份>/<地区>/          # 每份高考真题一个独立、可编译的目录
│   ├── <地区>.tex               # 本卷源文件（\chapter{<年份>年<地区>} + 一道题一个 \item）
│   ├── Makefile                 # 本卷编译/自查/软链接脚本
│   ├── figs/                    # 本卷图片（短名：题号+子图字母，如 03a.svg、10b.png）
│   ├── TikZ/                    # 人工重绘的 TikZ 图片（一张图一个 .tex，编译为 PDF）
│   └── README.md                # 【可选】本卷特殊要求
├── JSON/                        # 【本地·Git 忽略】平台 JSON 原始数据（<年>/<年_地区>.json + tiku_images/）
├── Docx/                        # 【本地·Git 忽略】平台 Word / PDF 原始文档（<年>/<年_地区>.docx/.pdf）
├── 材料处理/<年份>/<地区>/       # 【本地·Git 忽略】材料处理目录（PDF→markdown、OCR、图片提取；
│                                #   与 试卷/ 分离，含 ovis/ paddle/ pdftotext.txt merged.md pdfimages/ 等）
├── tools/                       # 脚本
│   ├── json_to_tex.py           # JSON → LaTeX 初稿 + 图片素材（制作第一步）
│   ├── check_paper.py           # 试卷规范自查（元数据/图片命令/标签/引用/答案）
│   ├── tex_links.py             # 为各卷目录建立公共文件相对软链接
│   ├── ocr_pipeline.sh          # PDF → Markdown 双引擎 + pdftotext 管线
│   ├── pdf_to_md.py             # 引擎甲 OvisOCR2（底本）
│   ├── PaddleOCR_PDF_to_md.py   # 引擎乙 PaddleOCR-VL（验证）
│   ├── material_merge.py        # 三路交叉验证生成 merged.md
│   ├── pdf_extract_images.py    # 从原 PDF 无损提取内嵌图（pdfimages 封装）
│   ├── check_material.py        # 材料四要素 / 图片引用 / 底稿漂移检查
│   ├── recrop_figures.py        # 多子图裁剪（recipe 驱动，调用 splitpicture）+ 前后对比
│   ├── match_figures.py         # 旧 figs 图 → 源内嵌图/裁剪框 匹配草表
│   ├── check_recrop.py          # 裁剪 recipe 一致性检查
│   ├── tikz_compare.py          # 重绘 TikZ 与原图的「重绘前后」对比图
│   ├── check_tikz.py            # TikZ/tikz_sources.json 原图登记一致性检查
│   ├── paddlex_serve_start.sh   # 启动 PaddleOCR-VL 服务
│   ├── paddlex_serve_stop.sh    # 关闭 PaddleOCR-VL 服务
│   └── README.md                # 脚本索引与用法
├── gaokaozhenti.cls             # 公共文档类（ctexbook + 公共宏包 + 列表样式）
├── ChoiceQuestion.sty           # 选择题 / 多图 / 答案与解析命令（项目共用）
├── PhyUnit.sty                  # 物理单位宏包
├── package/exam-zh-choices.sty  # 选项排版依赖
├── ChoiceQuestion-manual.md     # ChoiceQuestion.sty 使用说明
├── 高考物理真题制作规范.md        # 【核心】真题制作规范（结构/元数据/图片/答案/解析）
├── 材料处理与OCR规范.md          # PDF→Markdown 多引擎交叉验证与图片提取
├── 异常记录.md                   # 各卷异常与待人工核验记录
├── Makefile                     # 根目录批量编译脚本
└── README.md
```

> `JSON/`、`Docx/`、`材料处理/`、`svg-inkscape/`、`试卷/**/*.pdf`（编译产物）已在 `.gitignore` 中忽略，只保留在本地。
> 入库的是**可复现的源文件**（`.tex`、`.sty`、`.cls`、`figs/`、`Makefile`、文档）。

---

## 二、总流程（制作一份卷）

1. **取数据**：从 `JSON/<年>/<年_地区>.json` 得到基本材料（元信息、题干、选项、答案、图片）。
2. **转初稿**：`python3 tools/json_to_tex.py JSON/<年>/<年_地区>.json`
   —— 自动把图片按“题号+子图字母”复制到 `试卷/<年>/<地区>/figs/`，生成 `<地区>.tex` 初稿，
   并把 JSON 基础材料 markdown 写到 `材料处理/<年>/<地区>/json_material.md`。
3. **转 Markdown 交叉验证**（公式/表格/图片质量把关）：
   `tools/ocr_pipeline.sh Docx/<年>/<年_地区>.pdf 材料处理/<年>/<地区>`
   —— 用 **OvisOCR2（底本）+ PaddleOCR-VL（验证）+ pdftotext（旁证）** 生成 `merged.md`，
   并从原 PDF **无损提取内嵌图**到 `pdfimages/`。
   （材料统一放在根目录 `材料处理/<年>/<地区>/`，**不放进具体的 LaTeX 文档目录**。）
   （若该年地区**缺 PDF**，改用 `Docx` 中的 `.docx`：pandoc 转 Markdown 作为图解/解析参考。）
4. **逐题校对与补全**：以 JSON 为主、`merged.md` 与原 PDF 为准，逐题核对题干 / 数据 / 单位 /
   上下标 / 公式 / 选项与答案 / 填空答案 / 图片（子图拆分与摆放）/ **详解**；
   发现异常记入 `异常记录.md`。
5. **规范化排版**：按 `高考物理真题制作规范.md` 编写 `.tex`：
   `\chapter{…}` + 一个 `enumerate`、题目用 `\item`、小问嵌套 `enumerate`；
   图片一律用 `ChoiceQuestion` 的 `\onepicture/\twopicture/…`；
   答案用 `\xzanswer/\tkanswer/\jdanswer`；详解用 `\memoanswer`（可多人多条）。
6. **编译与自查**：在试卷目录执行 `make`（先编译 `TikZ/`，再编译正文），再执行 `make check`。

> **严禁在转换过程中引入 TikZ 重绘**：一律直接使用 JSON 中的图片数据；JSON 缺图时，
> 从对应 `.docx` / `.pdf` **无损提取**（优先 PDF）。确需 TikZ 重绘的图由人工查验并手绘
> （如 2026 湖北第 4 题），放入该卷 `TikZ/`。

---

## 三、编译方法

在**项目根目录**一键批量编译全部试卷：

```bash
make                # 编译全部试卷（每卷：TikZ 图片 + 正文 PDF）
make JOBS=8         # 并行 8 线程（各卷相互独立）
make tikz           # 仅编译各卷 TikZ/ 下的独立图片
make tikz-compare   # 生成各卷「重绘 TikZ 与原图」对比图（tikz_compare/）
make check          # 全部试卷规范自查 + TikZ 登记 + 裁剪 recipe + 材料完整性
make check-tikz     # 仅 TikZ 原图登记一致性检查
make links          # 为各卷目录建立指向根公共文件的相对软链接
make clean          # 清理各卷辅助文件
make distclean      # 清理各卷辅助文件与 PDF 成品

# 材料处理（PDF→markdown / OCR / 提图；需 Conda 环境与 PaddleOCR-VL 服务）
make material PDF=<源PDF> OUT=材料处理/<年>/<地区>   # 跑某卷的 OCR 材料管线
make material-merge   # 为 材料处理/ 下各卷生成/校验 merged.md
make extract-images   # 从源 PDF 无损提取内嵌图到 材料处理/…/pdfimages/
make check-material   # 材料四要素 / 图片引用 / 底稿漂移检查
```

也可进入单卷目录 `试卷/<年>/<地区>/` 单独编译：

```bash
make              # 编译本卷（TikZ + 正文）
make tikz         # 仅编译 TikZ 图片
make tikz-compare # 生成本卷重绘 TikZ 与原图对比图
make check        # 规范自查
make links        # 建立公共文件软链接（便于 TeXStudio 直接编译）
make clean / distclean
```

- 编译使用 `latexmk -xelatex -shell-escape`（`svg` 宏包需调用 Inkscape）。
- 公共样式（`gaokaozhenti.cls`、`PhyUnit.sty`、`ChoiceQuestion.sty`、`package/`）位于项目根，
  由 `TEXINPUTS` 引入，并可在各卷目录建立软链接后用编辑器直接编译。
- 编译产物（`*.pdf`、`TikZ/*.pdf`、`svg-inkscape/`）不入库，克隆后 `make` 重新生成。

---

## 四、规范文档

| 文档 | 内容 |
| :--- | :--- |
| `高考物理真题制作规范.md` | 文档结构、元数据字段与顺序、图片命令与引用标签、答案与解析、异常记录 |
| `材料处理与OCR规范.md` | PDF→Markdown 双引擎交叉验证、无损提取图片、底稿漂移检查 |
| `异常记录.md` | 各卷当前异常（缺详解、缺图、复合图待拆、回忆版等）与人工核验记录 |
| `ChoiceQuestion-manual.md` | `ChoiceQuestion.sty` 使用说明（选项 / 多图 / 答案解析） |

---

## 五、当前进度

| 年份 | 地区 | 状态 |
| :--- | :--- | :--- |
| 2026 | 云南 | 已完成：结构迁移、ChoiceQuestion 图片命令、OCR 校对、**全 15 题详解补全**、解析图回填、编译通过 |
| 2026 | 湖北 | 已完成：结构迁移、含人工重绘 TikZ 图 1 张、**全 15 题详解补全**、受力分析解析图回填、编译通过 |
| 2025 | 湖北 | 已完成：结构迁移、**全 15 题详解补全**、解析图回填、编译通过 |
| 2024 | 湖北 | 已完成：结构迁移、**全 15 题详解补全**、轨迹解析图回填、编译通过 |

> 4 套卷的材料位于 `材料处理/<年>/<地区>/`（`merged.md`、`pdftotext.txt`、`pdfimages/` 等），
> 已由 OvisOCR2 + PaddleOCR-VL + pdftotext 交叉验证产出（本地，不入库）。
> 详细的异常与人工核验记录见 `异常记录.md`。

其余年份/地区（2000—2026）的 JSON / Docx / PDF 已就位，按上述流程陆续制作。
