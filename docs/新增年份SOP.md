# 新增年份 / 制作一份卷 · 操作 SOP

> 依据 `高考物理真题制作规范.md`、`LaTeX_format_ReadMe.md`、`材料处理与OCR规范.md`。
> 本文件是可勾选清单；命令详见 `docs/编译方法.md`，异常/进度登记见 `异常记录.md` 与 `进度记录.md`。

## A. 制作一份卷（逐卷）

1. **取数**：`python3 tools/json_to_tex.py JSON/<年>/<年_地区>.json`
   （生成 `试卷/<年>/<地区>/<地区>.tex` 初稿与 `figs/`；初稿已自动补缺详解占位、
   非选择题 `\jdanswer`、多图/图片选项；**理综节选**加 `--renumber --paper-type 理综物理部分`）。
2. **材料处理**（有 PDF 时）：`make material PDF=Docx/<年>/<年_地区>.pdf OUT=材料处理/<年>/<地区>`；
   无 PDF 时登记到 `异常记录.md` 的“源文档缺失清单”，仅依 JSON 制作。
3. **逐题校对**：以 `merged.md` / JSON / 原 PDF 为准，核对题干、数据、单位、上下标、公式、选项与答案、
   图片（子图拆分与摆放）、详解；公式编号①②③与评分标准若原卷有则**忠实保留**。
4. **规范化排版**：单顶层 `enumerate`；13 项元数据；图片一律 ChoiceQuestion 命令；单位一律 PhyUnit；
   非选择题必须有 `\jdanswer`（多小问）或 `\tkanswer`（填空）；每题一条基本 `\memoanswer{}`。
5. **编译**：`cd 试卷/<年>/<地区> && make student && make teacher`（两版均须成功）。
6. **自查**：`make check`（结构/元数据、元数据↔JSON、答案对应、单位宏、内容、共性问题、版面、缺字、跨项复查）。
7. **登记**：更新 `进度记录.md` 对应行；在 `异常记录/<年>.md` 登记缺题/缺图/缺详解/公式疑误等；
   `make index`；`make check-docs`。

## B. 新增一个年份

1. `异常记录/` 下复制 `_模板.md` 为 `<年份>.md`（首行改为 `# 异常记录 · <年份> 年`）。
2. `进度记录.md` 新增 `### <年份> 年（N 套）` 小节与表头，逐卷加行（题数、状态、说明、异常链接）。
3. 完成 A 的各卷后执行 `make index`（生成 `试卷/<年份>/README.md`、刷新 README 概要）。
4. `make check-docs` 校验一致；`make progress` 查看含“欠账台账”的概要。

## C. 卷级标记（可选）

放在 `\chapter{…}` 之后、`\begin{enumerate}` 之前（注释，不参与排版；不进入题目元数据块）：

```latex
\chapter{2026年上海}
%% recalled: true          % 回忆版（题目不全）
%% paperType: 理综物理部分  % 特殊卷性质（如理综节选）
```

`make index` 会在年份索引中显示“标记”列。

## D. 提交前

- [ ] `make check` 全绿；`make tools-test` 通过；`make check-docs` 通过。
- [ ] `进度记录.md` / `异常记录/<年>.md` 已更新；`make index` 已刷新。
- [ ] 无构建产物入库（`*.pdf`、日志、`svg-inkscape/` 均已忽略）。
