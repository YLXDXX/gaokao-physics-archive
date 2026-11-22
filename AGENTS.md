# AGENTS.md

给在本仓库工作的 AI / 协作者：**动手前先读本文件**，再读
`高考物理真题制作规范.md`（核心）、`LaTeX_format_ReadMe.md`（排版）、
`材料处理与OCR规范.md`（材料/OCR）、`图片尺寸处理规范.md`（图片尺寸重排）、
`docs/新增年份SOP.md`（操作清单）。

> **工具使用与权限（所有会话，含子代理，均须遵守）**：
> ① 一律在**仓库根**执行命令，用 `make -C 试卷/…`，**不要 `cd`、不要用 `..`**；
> ② 临时文件与 **PDF 渲染页只写 `/tmp/opencode/`**；
> ③ 文件读写优先用 Read/Glob/Grep/Edit/Write，不要用 Bash 的 `cat/find/grep/sed` 代替；
> ④ 派发子任务时须在 prompt 中写明以上各点。
> 详细说明见 [`docs/AGENTS.md`](docs/AGENTS.md)（由**本地、不入库**的 `opencode.json`
> 经 `instructions` 加载；无该文件时以本段为准）。

## 仓库是什么

高考物理真题 LaTeX 档案库：每年/地区一份**可独立编译**的文档，
一份源文件经 `\gkver` 开关生成**学生版 + 教师版**；
题目均有元数据、答案与详解，图片一律用 `ChoiceQuestion` 命令，单位用 `PhyUnit`。

## 目录约定

- `试卷/<年>/<地区>/`：`<地区>.tex`、`Makefile`、`figs/`、`TikZ/`；`试卷/<年>/README.md` 为年份索引（**自动生成**）。
- `JSON/`、`OriginPDF/`、`材料处理/`：**本地、Git 忽略**（源数据与 OCR 产物）。
- `进度记录.md`：逐卷进度明细（人工维护表）；`异常记录/<年>.md`：按年异常（统一结构：
  `## 制作说明` + 状态分区表，待补充 → 待处理/处理中 → 待人工核验 → 已解决）；
  `异常记录.md`：总索引 + 跨年份说明。
- `docs/`：从 README 移出的编译方法与运行环境。
- `tools/`：转换、材料、检查、索引脚本；`tools/bin/`：并行编译包装（见 `tools/README.md`）。
- **OCR / 切图 / 尺寸 / TikZ 对比由独立 OCRPipeLine 提供**（`ocrpipe`，默认 `~/.local/bin/ocrpipe`）；
  本仓库不保留 OCR 流水线与切图程序，只保留使用说明软链接 `OCR识别转换流程说明.md`。

## 制作一份卷的固定顺序

```bash
python3 tools/json_to_tex.py JSON/<年>/<年_地区>.json        # 1 初稿 + 图片
# 2 对照 材料处理/<年>/<地区>/merged.md、原 PDF 逐题校对重写
# 2.5 图片尺寸专项（可选）：make figsize-audit / figsize-plan / figsize-apply / figsize-check；见 图片尺寸处理规范.md
make -C 试卷/<年>/<地区> student && make -C 试卷/<年>/<地区> teacher   # 3 两版编译
make -C 试卷/<年>/<地区> check                                # 4 自查（须 0 错误）
```

> 统一在**仓库根**执行命令，用 `make -C 试卷/…` 进入卷目录；**不要** `cd`。
> 新建卷目录时复制一份 `Makefile`（模板见任一已有卷）即可；`make`（含 `student`/`teacher`）
> 会自动执行 `tools/tex_links.py` 在本卷建立指向根公共文件的相对软链接（供 TeXStudio 直接编译）。

## 硬性规则（会被 `make check` 检查）

- 骨架：顶部 `\ifdefined\gkver\else\def\gkver{student}\fi` + `\documentclass[\gkver]{gaokaozhenti}`；
  单个顶层 `enumerate`；`\chapter{<年>年<地区>}`。
- 每题 `\item` 后 13 项元数据注释，顺序固定，**取值须与 JSON 一致**（`check_meta.py`）；
  PDF 补充题在 `%% duplicateId` 后加单 `%` 注释 `% pdf-only: true`。
- 答案：选择 `\xzanswer`/`\fourchoices[answer=]`/`%% answer` 三处一致；
  非选择题必须有 `\jdanswer`（多小问）或 `\tkanswer`（填空）；计算题答案 `enumerate` 与小问一一对应，
  实验题答案可在 `\jdanswer` 内手动编号对应（`check_answers.py`）。
- 每题一条基本 `\memoanswer{}`；缺原卷详解时写 `\memoanswer{本题原卷及材料中未提供详解，待补充。}` 并登记异常。
- 图片只用 ChoiceQuestion 命令（`\onepicture`/`\twopicture`/`\fourchoices[ispicture=true]`），路径 `figs/`，
  尺寸用绝对 cm；**严禁 TikZ 重绘**（确需人工手绘并登记）。
- 单位一律 `PhyUnit` 宏（`check_units.py` 校验未定义宏；`check_content.py` 查裸单位）。
- 公式用 `\frac`（禁 `\dfrac`）；核素/化学式用 `\ce{}`；数字间半角冒号；`$x-t$` 不为 `$x$-$t$`。
- 不手工编号（列表/图片自动编号）；版面微调用 `\gknewpage` 等，不用原生 `\newpage/\vfill/\hfil`。

## 共享宏包（外部项目软链接）

- 根目录 `ChoiceQuestion.sty`、`ChoiceQuestion-manual.md`、`PhyUnit.sty`、`PhyUnit-manual.md`
  是维护者本地指向同级项目 `../ChoiceQuestion/`、`../PhyUnit/` 的**相对软链接**；
  本仓库不再保存副本，`package/` 已移除（ChoiceQuestion v0.12 已内置原 exam-zh-choices）。
- 修改宏包/单位宏等同于修改对应外部项目：应修改 `../ChoiceQuestion/` 或 `../PhyUnit/`
  中的源文件，并同步更新其手册/README、重新编译测试；需要时在那些项目单独提交。
- 只改本仓库内容时，不要删除或替换这些软链接；外部克隆若无同级项目，需自行放置对应版本。

## 收尾

```bash
make index          # 刷新 试卷/<年>/README.md 与 README 进度概要
make check-docs     # 进度 / 年份索引 / 异常记录 一致性
make progress       # 查看各年概要 + 欠账台账（未闭合异常、缺详解）
make tools-test     # 工具单元测试
make fetch-pr PR=1  # 接取协作者 PR 到本地分支 pr/1（审查，见 docs/代码审查指南.md）
make pr-check PR=1  # 接取并对 PR 改动卷先 make all 再 check
```

- 新增/更新异常写入 `异常记录/<年>.md`（统一结构：`## 制作说明` + 状态分区表，表头
  `地区|题号|类别|问题|处理建议|状态`，`已解决` 置末），并在 `进度记录.md` 更新该卷行。
- **不要**手工编辑 `试卷/<年>/README.md`（由 `make index` 生成）。
- 只改自己负责的目录，避免动共享文件（`tools/`、`*.sty`、`*.cls`、文档）引起冲突。
