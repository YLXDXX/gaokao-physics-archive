# gaokao-physics-archive

高考物理真题 · LaTeX 档案库。

收集各年份、各地区的高考物理真题，按**统一版式与规范**制作成一份份**可独立编译**的
LaTeX 文档，并为每道题保留**元数据**与**详解**，为后续高质量高考真题库建设提供数据基础。

项目地址：

- Gitee：[https://gitee.com/ylxdxx/gaokao-physics-archive](https://gitee.com/ylxdxx/gaokao-physics-archive)
- Github：[https://github.com/YLXDXX/gaokao-physics-archive](https://github.com/YLXDXX/gaokao-physics-archive)

> 本项目的若干工程经验：
> **去中心化**（每份卷独立目录、独立 `Makefile`、独立图片）、公共样式只在根目录一份、
> 材料处理采用**双 OCR 引擎（OvisOCR3 + PaddleOCR-VL）+ pdftotext 交叉验证**、题目统一以 `ChoiceQuestion.sty`
> 的选择题命令图片命令与答案/解析命令排版、各内容统一使用 `PhyUnit.sty` 排版物理单位。

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
├── OriginPDF/                   # 【本地·Git 忽略】平台 PDF 原始文档（<年>/<年_地区>.pdf）
├── 材料处理/<年份>/<地区>/       # 【本地·Git 忽略】材料处理目录（PDF→markdown、OCR、图片提取；
│                                #   与 试卷/ 分离，含 source.json、ovis/、paddle/、pdftotext.txt、merged.md、pdfimages/ 等）
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
│   ├── tex_links.py             # 为各卷目录建立公共文件相对软链接（make 时自动执行）
│   ├── bin/inkscape             # Inkscape 串行化包装（并行编译用；各卷 Makefile 已加入 PATH）
│   ├── （切图：`ocrpipe recrop/match/check-recrop`，见 OCR识别转换流程说明.md）
│   ├── （TikZ 对比/登记：`ocrpipe tikz-compare/check-tikz`，见 OCR识别转换流程说明.md）
│   ├── gen_index.py             # 索引/进度生成与共享库（make index）
│   ├── check_docs.py            # 进度/年份索引/异常记录一致性校验（make check-docs）
│   ├── check_docs_text.py       # 文档体检（过时 cd 用法 / 失效相对链接）
│   ├── review_to_ledger.py      # 复核结果 JSON → 异常记录台账
│   ├── status.py                # 各年份进度概要（make progress）
│   └── README.md                # 脚本索引与用法
├── docs/                        # 从 README 移出的细则
│   ├── 新增年份SOP.md            # 新增年份 / 制作一份卷的操作清单
│   ├── 编译方法.md               # 批量/单卷编译命令、两版开关、版面微调
│   ├── 代码审查指南.md           # 接收协作者 PR 的接取/审查流程（维护者）
│   ├── 运行环境.md               # TeX / 字体 / poppler / splitpicture / OCR / Python
│   └── AGENTS.md                # 工具使用与权限约定（经本地 opencode.json 加载）
├── gaokaozhenti.cls             # 公共文档类（ctexbook + 公共宏包 + 列表样式）
├── ChoiceQuestion.sty           # 软链接 → ../ChoiceQuestion/ChoiceQuestion.sty
├── PhyUnit.sty                  # 软链接 → ../PhyUnit/PhyUnit.sty
├── ChoiceQuestion-manual.md     # 软链接 → ../ChoiceQuestion/ChoiceQuestion-manual.md
├── PhyUnit-manual.md            # 软链接 → ../PhyUnit/PhyUnit-manual.md
├── CONTRIBUTING.md              # 面向人类协作者的贡献指南（提交前自查、禁提交项）
├── .gitee/PULL_REQUEST_TEMPLATE.md  # Gitee PR 模板（自查清单）
├── .github/pull_request_template.md # GitHub 镜像版 PR 模板（同款清单）
├── AGENTS.md                    # 给 AI / 协作者的仓库约定与制作顺序（入口）
├── 高考物理真题制作规范.md        # 【核心】真题制作规范（结构/元数据/图片/答案/解析）
├── LaTeX_format_ReadMe.md        # LaTeX 文档格式基本要求（排版细则，全卷共用）
├── 材料处理与OCR规范.md          # PDF→Markdown 多引擎交叉验证与图片提取
├── 图片尺寸处理规范.md           # 图片按源 PDF 物理尺寸重排的流程/策略/登记格式
├── OCR识别转换流程说明.md        # 软链接 → OCRPipeLine/docs/USAGE.md（外部程序使用说明）
├── 进度记录.md                   # 各年份/地区制作进度明细（README 只留概要）
├── 异常记录.md                   # 异常记录总索引 + 跨年份通用说明
├── 异常记录/<年份>.md             # 每一年各卷异常（统一：制作说明 + 待补充/待人工核验/已解决 分区表）
├── Makefile                     # 根目录批量编译脚本
├── ocr_pipeline.json            # OCRPipeLine 项目配置（base_roots=OriginPDF）
├── figure_spec.json             # 图片尺寸全局配置（版心 170mm、scale_mode=auto）
└── README.md
```

> `ChoiceQuestion.sty`、`ChoiceQuestion-manual.md`、`PhyUnit.sty`、`PhyUnit-manual.md`
> 在维护者本地是指向同级项目 `../ChoiceQuestion/`、`../PhyUnit/` 的相对软链接，便于统一修改；
> 修改宏包/单位宏应在对应外部项目内完成并同步其手册/README，必要时在那些项目提交；
> 外部克隆若无同级项目，请自行放置对应版本的宏包/说明文件。
> `package/` 已移除（ChoiceQuestion v0.12 已内置原 exam-zh-choices）。
>
> `JSON/`、`OriginPDF/`、`材料处理/`、`svg-inkscape/`、图片尺寸工作文件（`figures.map.json`、`figures.manifest.json`、`figsizes.json`）与各卷**编译产物**（`*_学生版.pdf`/`*_教师版.pdf`、
> `TikZ/*.pdf` 等）已在 `.gitignore` 中忽略，只保留在本地；**`试卷/**/figs/*.pdf` 是源图，已入库**。
> 入库的是**可复现的源文件**（`.tex`、`.sty`、`.cls`、`figs/`、`Makefile`、文档）。

---

## 二、总流程（制作一份卷）

1. **取数据**：从 `JSON/<年>/<年_地区>.json` 得到基本材料（元信息、题干、选项、答案、图片）。
2. **转初稿**：`python3 tools/json_to_tex.py JSON/<年>/<年_地区>.json`
   —— HTML/公式经 `tools/html2latex.py` 转为 LaTeX，图片按“题号+子图字母”复制到
   `试卷/<年>/<地区>/figs/`，生成 `<地区>.tex` 初稿。
3. **转 Markdown 交叉验证**（公式/表格/图片质量把关）：
   `make material PDF=OriginPDF/<年>/<年_地区>.pdf OUT=材料处理/<年>/<地区>`
   （等价：`ocrpipe run -c ocr_pipeline.json -i … -o … --auto-serve`）
   —— 用 **OvisOCR3（底本）+ PaddleOCR-VL（验证）+ pdftotext（旁证）** 生成 `merged.md`，
   并从原 PDF **无损提取内嵌图**到 `pdfimages/`；批量用
   `make material-batch ARGS="--auto-serve"`（断点续跑，筛选改用 `--only 2026/湖北`）。
   （材料统一放在根目录 `材料处理/<年>/<地区>/`，**不放进具体的 LaTeX 文档目录**。）
   （若该年地区**缺 PDF**，仅依 JSON 制作，并在 `异常记录/<年份>.md` 登记；补齐 PDF 后重做材料与图片。）
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
> 从对应 `.pdf` **无损提取**。确需 TikZ 重绘的图由人工查验并手绘
> （如 2026 湖北第 4 题），放入该卷 `TikZ/`。

> **图片尺寸专项**（批量/复核）：先 `make figsize-status`，**done 的卷跳过**；再按
> `图片尺寸处理规范.md` 建立 `figures.map.json`，依次 `figsize-plan` → `figsize-apply --write` → `figsize-check`；
> 扫描 PDF 只作尺寸参考，不替换 JSON 清晰图。

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
make fetch-pr PR=1   # 接取 Gitee PR 到本地分支 pr/1（审查用，见 docs/代码审查指南.md）
make pr-check PR=1   # 接取并对 PR 改动卷先 make all 再 check
```

> **并行编译（已支持）**：含 `\includesvg` 的卷每张 SVG 都会调用 Inkscape；多个进程并发
> 调用 Inkscape 会因 `Gio::DBus::Error` 随机崩溃。各卷 Makefile 已把 `tools/bin/inkscape`
> （`flock` 串行化包装）加入 `PATH`，因此 `make JOBS=8` / `make -jN` 可**安全并行**。
> 若曾并行失败：latexmk 会把错误记入 `*.fdb_latexmk`，请先 `make distclean` 再重编。
>
> **软链接（TeXStudio）**：`make`（及各卷 `make student/teacher`）会**自动在每卷目录建立**
> 指向根公共文件（`gaokaozhenti.cls`/`PhyUnit.sty`/`ChoiceQuestion.sty`）的相对软链接，
> 因此可直接用 TeXStudio 打开某卷 `.tex` 编译，无需额外配置。


---

## 四、规范文档

| 文档 | 内容 |
| :--- | :--- |
| `AGENTS.md` | 给 AI / 协作者的仓库约定、目录与制作顺序（入口） |
| `CONTRIBUTING.md` | 面向人类协作者的贡献指南（制作摘要、提交前自查、禁提交项、TikZ 重绘登记） |
| `高考物理真题制作规范.md` | 【核心】文档结构、元数据字段与顺序、图片命令与引用标签、答案与解析、异常记录 |
| `LaTeX_format_ReadMe.md` | LaTeX 文档格式基本要求（排版细则：两版开关、答案命令、图片与编号、公式单位、段落分行等） |
| `材料处理与OCR规范.md` | PDF→Markdown 双引擎交叉验证、逐页版面源数据、无损提取图片、底稿漂移检查 |
| `图片尺寸处理规范.md` | 按源 PDF 物理尺寸重排图片：replace/measure/manual 三策略、扫描件仅作参考、manifest 与验收 |
| `OCR识别转换流程说明.md` | 外部 OCRPipeLine 使用说明（软链接）：安装、OvisOCR3 + PaddleOCR-VL、逐页源数据、断点续跑、Paddle 自动分块 |
| `docs/新增年份SOP.md` | 新增年份 / 制作一份卷的可勾选清单 |
| `docs/编译方法.md` | 批量/单卷编译命令、两版开关、版面微调 |
| `docs/代码审查指南.md` | 接收协作者 PR：`make fetch-pr`/`pr-check`、审查流程、项目专属清单（维护者） |
| `docs/运行环境.md` | TeX / 字体 / poppler / splitpicture / OCR / Python |
| `docs/AGENTS.md` | 工具使用与权限约定（工作目录固定在仓库根、临时/渲染文件只放 `/tmp/opencode/`、子代理约定；由本地 `opencode.json` 加载） |
| `进度记录.md` | 各年份/地区制作进度明细（题数、状态、说明、异常链接） |
| `异常记录.md` | 异常记录总索引 + 跨年份通用说明（材料处理结论、通用风险、更新方式） |
| `异常记录/<年份>.md` | 每一年各卷异常；统一结构：`## 制作说明` + 状态分区表（待补充 → 待处理/处理中 → 待人工核验 → 已解决，**已解决置末**） |
| `ChoiceQuestion-manual.md` | `ChoiceQuestion.sty` 使用说明（选项 / 多图 / 答案解析） |
| `tools/splitpicture使用说明.md` | 外部 `splitpicture` 在本项目的用法（检测模式 / 标签擦除 / CLI 与 GUI / 难例调参） |
| `tools/textfix/README.md` | 共性问题正则修正模块说明（规则 / 用法 / 测试） |

---

## 五、当前进度

> **明细见 [`进度记录.md`](进度记录.md)**；此处只保留总体概要（由 `make index` 自动刷新）。

<!-- PROGRESS:START -->
- **已完成**：49 个年份、共 **413 套**卷、**6735 题**（1978 年 1 套、1979 年 1 套、1980 年 1 套、1981 年 1 套、1982 年 1 套、1983 年 1 套、1984 年 1 套、1985 年 2 套、1986 年 2 套、1987 年 1 套、1988 年 2 套、1989 年 2 套、1990 年 2 套、1991 年 3 套、1992 年 3 套、1993 年 2 套、1994 年 2 套、1995 年 2 套、1996 年 2 套、1997 年 2 套、1998 年 2 套、1999 年 3 套、2000 年 7 套、2001 年 8 套、2002 年 8 套、2003 年 8 套、2004 年 13 套、2005 年 11 套、2006 年 11 套、2007 年 14 套、2008 年 14 套、2009 年 17 套、2010 年 16 套、2011 年 14 套、2012 年 14 套、2013 年 15 套、2014 年 15 套、2015 年 14 套、2016 年 12 套、2017 年 10 套、2018 年 10 套、2019 年 9 套、2020 年 11 套、2021 年 17 套、2022 年 17 套、2023 年 18 套、2024 年 22 套、2025 年 25 套、2026 年 24 套）。
- **材料就位**：`材料处理/` 已对 `OriginPDF/` 下 406 份 PDF 完成三路转换与提图（详见 `异常记录.md`）；2026-11-22 又补齐 7 份源 PDF（1992 湖南云南海南、2000 天津/广东/苏浙吉、2001 粤豫、2003 全国理综旧课程/广东广西），并已完成材料处理、内容补全与校对；图片尺寸已完成 2026–2013 十四个年份共 219 套（全库累计 224/413 套）；2026-11-23 完成十四年度专项（2026–2013；逐卷 figures.manifest.json、pHYs 回填、双版编译与 make check 通过），其余年份待后续专项。`OriginPDF/` 已覆盖 413/413 套，当前无缺失 PDF。
- **待制作**：无（各年份/地区均已制卷；按批次持续复核、补全缺详解）。
<!-- PROGRESS:END -->

各卷异常与人工核验事项按年份记录在 `异常记录/<年份>.md`（索引见 [`异常记录.md`](异常记录.md)）。

---

## 六、运行环境

TeX / 中文字体自动回退 / poppler / splitpicture / OCR / Python 依赖等详见
**[`docs/运行环境.md`](docs/运行环境.md)**。要点：本地 TeX Live 2025（`xelatex` + `latexmk`，
`svg` 经 Inkscape，编译开启 `-shell-escape`）；中文字体在有/无 Windows 字体的系统均可编译；
OCR/材料转换由独立 **OCRPipeLine** 提供（`ocrpipe`，默认安装到 `~/.local/bin`），
需 Conda 环境与 PaddleOCR-VL 服务；安装与用法见 `OCR识别转换流程说明.md`。

## 七、一点说明

特别感谢上海第八中学的范老师，他分门别类对各年高考题做了精心整理，无私分享，提供了本项目最基本的原始材料，他的小站 [enjoyphysics.cn](https://enjoyphysics.cn/) 做得很好，大家可以去看一下。

高考真题库的建议当前还有大量工作未完成，需要各位的通力合作，现需刷题、校对、排版、制图、编程等各方面人手，感兴趣的小伙伴可以通过邮件（ylxdxx@qq.com）联系我。

愿:

> 古今共栽树，天下齐乘凉

---

