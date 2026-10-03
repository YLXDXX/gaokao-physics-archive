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
│   │                            #   顶部 \gkver 开关：学生版（默认）/ 教师版同一源文件
│   ├── Makefile                 # 本卷编译/自查/软链接脚本（make student / make teacher）
│   ├── figs/                    # 本卷图片（短名：题号+子图字母，如 03a.svg、10b.png）
│   ├── TikZ/                    # 人工重绘的 TikZ 图片（一张图一个 .tex，编译为 PDF）
│   └── README.md                # 【可选】本卷特殊要求
├── 试卷/<年份>/README.md         # 年份索引（tools/gen_index.py 生成，列出本年各卷）
├── JSON/                        # 【本地·Git 忽略】平台 JSON 原始数据（<年>/<年_地区>.json + tiku_images/）
├── Docx/                        # 【本地·Git 忽略】平台 Word / PDF 原始文档（<年>/<年_地区>.docx/.pdf）
├── 材料处理/<年份>/<地区>/       # 【本地·Git 忽略】材料处理目录（PDF→markdown、OCR、图片提取；
│                                #   与 试卷/ 分离，含 ovis/ paddle/ pdftotext.txt merged.md pdfimages/ 等）
├── tools/                       # 脚本
│   ├── json_to_tex.py           # JSON → LaTeX 初稿 + 图片素材（制作第一步）
│   ├── html2latex.py            # HTML/公式 → LaTeX 的 DOM 转换器（json_to_tex 调用）
│   ├── check_paper.py           # 试卷规范自查（元数据/图片命令/标签/引用/答案）
│   ├── check_content.py         # 内容书写检查（裸单位/图片公式/段落分行提示）
│   ├── check_meta.py            # 元数据 ↔ 平台 JSON 逐字段一致
│   ├── check_answers.py         # 非选择题答案与小问对应
│   ├── check_formula_numbers.py # 解析公式编号 ①②③… 连续/悬空检查
│   ├── check_units.py           # PhyUnit 单位宏检查
│   ├── check_review.py          # 成品跨项复查（答案三处一致/解析引图/引用标签）
│   ├── check_glyphs.py          # 编译日志缺字检查
│   ├── check_layout_cmds.py     # 版面微调命令（禁用原生命令）检查
│   ├── tex_to_json.py           # 成品 .tex → 档案 JSON（反向抽取）
│   ├── textfix/                 # 共性问题正则修正模块（含规则、命令行与测试）
│   ├── test_*.py                # 工具单元测试（make tools-test）
│   ├── tex_links.py             # 为各卷目录建立公共文件相对软链接
│   ├── ocr_pipeline.sh          # PDF → Markdown 双引擎 + pdftotext 管线（单份）
│   ├── ocr_batch.py             # 批量材料处理驱动（分阶段、断点续跑）
│   ├── ocr_pipeline_all.sh      # 全库一键编排（自动启停服务、失败即停）
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
│   ├── gen_index.py             # 索引/进度生成与共享库（make index）
│   ├── check_docs.py            # 进度/年份索引/异常记录一致性校验（make check-docs）
│   ├── check_docs_text.py       # 文档体检（过时 cd 用法 / 失效相对链接）
│   ├── review_to_ledger.py      # 复核结果 JSON → 异常记录台账
│   ├── status.py                # 各年份进度概要（make progress）
│   └── README.md                # 脚本索引与用法
├── docs/                        # 从 README 移出的细则
│   ├── 新增年份SOP.md            # 新增年份 / 制作一份卷的操作清单
│   ├── 编译方法.md               # 批量/单卷编译命令、两版开关、版面微调
│   ├── 运行环境.md               # TeX / 字体 / poppler / splitpicture / OCR / Python
│   └── AGENTS.md                # 工具使用与权限约定（经本地 opencode.json 加载）
├── gaokaozhenti.cls             # 公共文档类（ctexbook + 公共宏包 + 列表样式）
├── ChoiceQuestion.sty           # 选择题 / 多图 / 答案与解析命令（项目共用）
├── PhyUnit.sty                  # 物理单位宏包
├── package/exam-zh-choices.sty  # 选项排版依赖
├── ChoiceQuestion-manual.md     # ChoiceQuestion.sty 使用说明
├── AGENTS.md                    # 给 AI / 协作者的仓库约定与制作顺序（入口）
├── 高考物理真题制作规范.md        # 【核心】真题制作规范（结构/元数据/图片/答案/解析）
├── LaTeX_format_ReadMe.md        # LaTeX 文档格式基本要求（排版细则，全卷共用）
├── 材料处理与OCR规范.md          # PDF→Markdown 多引擎交叉验证与图片提取
├── 进度记录.md                   # 各年份/地区制作进度明细（README 只留概要）
├── 异常记录.md                   # 异常记录总索引 + 跨年份通用说明
├── 异常记录/<年份>.md             # 每一年各卷异常与待人工核验记录（一年一个文件）
├── Makefile                     # 根目录批量编译脚本
└── README.md
```

> `JSON/`、`Docx/`、`材料处理/`、`svg-inkscape/`、`试卷/**/*.pdf`（编译产物）已在 `.gitignore` 中忽略，只保留在本地。
> 入库的是**可复现的源文件**（`.tex`、`.sty`、`.cls`、`figs/`、`Makefile`、文档）。

---

## 二、总流程（制作一份卷）

1. **取数据**：从 `JSON/<年>/<年_地区>.json` 得到基本材料（元信息、题干、选项、答案、图片）。
2. **转初稿**：`python3 tools/json_to_tex.py JSON/<年>/<年_地区>.json`
   —— HTML/公式经 `tools/html2latex.py` 转为 LaTeX，图片按“题号+子图字母”复制到
   `试卷/<年>/<地区>/figs/`，生成 `<地区>.tex` 初稿。
3. **转 Markdown 交叉验证**（公式/表格/图片质量把关）：
   `tools/ocr_pipeline.sh Docx/<年>/<年_地区>.pdf 材料处理/<年>/<地区>`
   —— 用 **OvisOCR2（底本）+ PaddleOCR-VL（验证）+ pdftotext（旁证）** 生成 `merged.md`，
   并从原 PDF **无损提取内嵌图**到 `pdfimages/`。
   （材料统一放在根目录 `材料处理/<年>/<地区>/`，**不放进具体的 LaTeX 文档目录**。）
   （若该年地区**缺 PDF**，改用 `Docx` 中的 `.docx`：pandoc 转 Markdown 作为图解/解析参考。）
4. **逐题校对与补全**：以 JSON 为主、`merged.md` 与原 PDF 为准，逐题核对题干 / 数据 / 单位 /
   上下标 / 公式 / 选项与答案 / 填空答案 / 图片（子图拆分与摆放）/ **详解**；
   发现异常记入 `异常记录/<年份>.md`。
5. **规范化排版**：按 `高考物理真题制作规范.md` 与 `LaTeX_format_ReadMe.md` 编写 `.tex`：
   源文件顶部 `\gkver` 开关（学生版默认）→ `\documentclass[\gkver]{gaokaozhenti}`；
   `\chapter{…}` + 一个 `enumerate`、题目用 `\item`、小问嵌套 `enumerate`；
   图片一律用 `ChoiceQuestion` 的 `\onepicture/\twopicture/…`；
   答案用 `\xzanswer/\tkanswer/\jdanswer`；详解用 `\memoanswer`（可多人多条）。
6. **编译与自查**：在仓库根执行 `make -C 试卷/<年>/<地区> all`（先编译 `TikZ/`，再生成
   **学生版 + 教师版**两份 PDF），再执行 `make -C 试卷/<年>/<地区> check`。
   学生版 `answer_shown=false`（答案留空、详解不显示），
   教师版 `answer_shown=true`（含答案与详解）。

> **严禁在转换过程中引入 TikZ 重绘**：一律直接使用 JSON 中的图片数据；JSON 缺图时，
> 从对应 `.docx` / `.pdf` **无损提取**（优先 PDF）。确需 TikZ 重绘的图由人工查验并手绘
> （如 2026 湖北第 4 题），放入该卷 `TikZ/`。

---

## 三、编译方法

**批量编译**（项目根目录）与**单卷编译**（`试卷/<年>/<地区>/`）的完整命令、两版开关
（学生版 / 教师版）、版面微调命令等详见 **[`docs/编译方法.md`](docs/编译方法.md)**。

```bash
make              # 编译全部试卷（TikZ + 学生版 + 教师版）
make JOBS=8       # 并行 8 线程
make check        # 规范自查 + 内容 + 共性问题 + 缺字 + 成品复查 + 文档索引校验
make index        # 刷新 试卷/<年>/README.md 与 README 进度概要
make progress     # 打印各年份进度概要
```


---

## 四、规范文档

| 文档 | 内容 |
| :--- | :--- |
| `AGENTS.md` | 给 AI / 协作者的仓库约定、目录与制作顺序（入口） |
| `高考物理真题制作规范.md` | 【核心】文档结构、元数据字段与顺序、图片命令与引用标签、答案与解析、异常记录 |
| `LaTeX_format_ReadMe.md` | LaTeX 文档格式基本要求（排版细则：两版开关、答案命令、图片与编号、公式单位、段落分行等） |
| `材料处理与OCR规范.md` | PDF→Markdown 双引擎交叉验证、无损提取图片、底稿漂移检查 |
| `docs/新增年份SOP.md` | 新增年份 / 制作一份卷的可勾选清单 |
| `docs/编译方法.md` | 批量/单卷编译命令、两版开关、版面微调 |
| `docs/运行环境.md` | TeX / 字体 / poppler / splitpicture / OCR / Python |
| `docs/AGENTS.md` | 工具使用与权限约定（工作目录固定在仓库根、临时/渲染文件只放 `/tmp/opencode/`、子代理约定；由本地 `opencode.json` 加载） |
| `进度记录.md` | 各年份/地区制作进度明细（题数、状态、说明、异常链接） |
| `异常记录.md` | 异常记录总索引 + 跨年份通用说明（材料处理结论、通用风险、更新方式） |
| `异常记录/<年份>.md` | 每一年各卷当前异常（缺详解、缺图、复合图待拆、回忆版等）与人工核验记录 |
| `ChoiceQuestion-manual.md` | `ChoiceQuestion.sty` 使用说明（选项 / 多图 / 答案解析） |
| `tools/splitpicture使用说明.md` | 外部 `splitpicture` 在本项目的用法（检测模式 / 标签擦除 / CLI 与 GUI / 难例调参） |
| `tools/textfix/README.md` | 共性问题正则修正模块说明（规则 / 用法 / 测试） |

---

## 五、当前进度

> **明细见 [`进度记录.md`](进度记录.md)**；此处只保留总体概要（由 `make index` 自动刷新）。

<!-- PROGRESS:START -->
- **已完成**：18 个年份、共 **265 套**卷、**4147 题**（2000 年 7 套、2008 年 14 套、2011 年 14 套、2012 年 14 套、2013 年 15 套、2014 年 15 套、2015 年 14 套、2016 年 12 套、2017 年 10 套、2018 年 10 套、2019 年 9 套、2020 年 11 套、2021 年 17 套、2022 年 17 套、2023 年 18 套、2024 年 22 套、2025 年 25 套、2026 年 21 套）。
- **材料就位**：`材料处理/` 已完成 402 份 PDF 的三路转换与提图（本地，不入库）。
- **待制作**：其余年份/地区，按批次推进。
<!-- PROGRESS:END -->

各卷异常与人工核验事项按年份记录在 `异常记录/<年份>.md`（索引见 [`异常记录.md`](异常记录.md)）。

```text
2026: 云南 湖北 湖南 广东 四川        2025: 湖北        2024: 湖北
2008: 上海 江苏 海南 全国理综Ⅰ 全国理综Ⅱ 北京理综 上海理综 四川理综
      天津理综 宁夏理综 山东理综 广东理综 广东理科基础 重庆理综
2000: 上海 全国旧课程 全国新课程 北京 天津 广东 苏浙吉
```

---

## 六、运行环境

TeX / 中文字体自动回退 / poppler / splitpicture / OCR / Python 依赖等详见
**[`docs/运行环境.md`](docs/运行环境.md)**。要点：本地 TeX Live 2025（`xelatex` + `latexmk`，
`svg` 经 Inkscape，编译开启 `-shell-escape`）；中文字体在有/无 Windows 字体的系统均可编译；
材料处理脚本需 Conda 环境与 PaddleOCR-VL 服务。
