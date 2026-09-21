# ChoiceQuestion.sty 使用说明

版本 0.3b ｜ 面向中文试卷（`ctex` 文档类）的选择题 / 多图 / 答案解析辅助宏包

---

## 1. 简介

`ChoiceQuestion` 在 `exam-zh-choices` 提供的选项环境之上封装了：

- 数量固定、写法简洁的选择题命令 `\twochoices` … `\ninechoices`；
- 图片选项的统一 / 单项尺寸控制与自动缩放；
- 多图排版命令 `\onepicture` … `\eightpicture`，按图片实际宽度自动分行
  （三图还会额外尝试非相邻两图配对），并支持标题、编号与 `\ref` / `\figref`
  引用，以及每行左/中/右对齐、隐藏“图a”前缀；
- 答案与解析命令：`\tkanswer`、`\xzanswer`、`\drawpicanswer`、`\memoanswer`、`\jdanswer`；
- 与 `beamer` 的自动配合（答案用 overlay 分步显示）。

宏包内部使用 `expl3` 编写，所有键值解析基于 `l3keys`。

---

## 2. 依赖与安装

必需依赖：`expl3`、`exam-zh-choices`、`xeCJKfntef`、`graphicx`、`xcolor`、
`tcolorbox`（含 `skins,breakable` 库）。

本地使用时，把 `ChoiceQuestion.sty` 与 `package/exam-zh-choices.sty` 放在主文件同目录即可。
若已从 CTAN 正式安装 `exam-zh-choices`，可把宏包中的

```latex
\RequirePackage{package/exam-zh-choices}
```

改为

```latex
\RequirePackage{exam-zh-choices}
```

以消除“名称不匹配”的警告（不影响功能）。

---

## 3. 快速开始

```latex
\documentclass[UTF8]{ctexbook}
\usepackage[answer_shown=true]{ChoiceQuestion}
\begin{document}
\fourchoices[answer=C]{选项甲}{选项乙}{选项丙}{选项丁}
\end{document}
```

用 XeLaTeX 编译两遍（第二遍解析 `\ref`）。

---

## 4. 加载选项

| 键 | 取值 | 说明 |
| --- | --- | --- |
| `answer_shown` | `true` / `false` | 是否显示答案，默认 `false` |
| `answer_color` | 颜色名 | 答案高亮颜色，默认 `AnswerGreen` |

示例：

```latex
\usepackage[answer_shown=true,answer_color=red]{ChoiceQuestion}
```

---

## 5. 选择题命令

### 5.1 命令一览

| 命令 | 含义 |
| --- | --- |
| `\twochoices[键]{A}{B}` | 2 个选项 |
| `\threechoices` | 3 个选项 |
| `\fourchoices` | 4 个选项 |
| `\fivechoices` | 5 个选项 |
| `\sixchoices` | 6 个选项 |
| `\sevenchoices` | 7 个选项 |
| `\eightchoices` | 8 个选项 |
| `\ninechoices` | 9 个选项（用法见下） |

`\ninechoices` 的写法与其它略有不同：第一个可选参数之后直接跟 9 个花括号选项。

```latex
\ninechoices[answer=I]{甲}{乙}{丙}{丁}{戊}{己}{庚}{辛}{壬}
```

### 5.2 键值

| 键 | 取值 | 说明 |
| --- | --- | --- |
| `answer` | 字母串，如 `A`、`BE` | 正确选项；默认 `Z`（不匹配任何项） |
| `color` | 颜色名 | 逐题答案高亮色，覆盖宏包级 `answer_color` |
| `ispicture` | `true` / `false` | 选项是否为图片，默认 `false` |

多选：`\fourchoices[answer=BD]{...}{...}{...}{...}` 会同时高亮 B、D 两项。

### 5.3 图片尺寸键

当 `ispicture=true` 时可用以下尺寸键（与多图命令共用同一套）：

| 键 | 取值 | 说明 |
| --- | --- | --- |
| `h` / `height` | 长度 | 所有选项统一高度 |
| `w` / `width` | 长度 | 所有选项统一宽度 |
| `hA`…`hI` | 长度 | 第 1~9 项单独高度（优先于全局） |
| `wA`…`wI` | 长度 | 第 1~9 项单独宽度（优先于全局） |
| `keepaspectratio` | `true` / `false` | 同时给 h、w 时是否等比，默认 `true` |

选项内容处理规则：

1. 纯文件名（不含控制序列）→ 自动包裹 `\includegraphics[尺寸]{文件}`；
2. 已含 `\includegraphics` → 把尺寸注入其可选参数（放在最前，用户显式参数可覆盖）；
3. 其它内容（`\rule`、`tikz` 等）→ 用 `\resizebox` 按尺寸缩放。

---

## 6. 多图命令

### 6.1 命令一览

`\onepicture` … `\eightpicture`，第 n 个命令接受 n 个必选参数
（图片文件名、`\includegraphics` 或任意内容）。内容处理规则与图片选项相同：
纯文件名自动包裹 `\includegraphics`，已含 `\includegraphics` 则注入尺寸，
其它内容用 `\resizebox` 缩放（见 5.3 节）。

```latex
\threepicture[w=0.28\linewidth, capA=甲, capB=乙, capC=丙]
  {example-image-a}{example-image-b}{example-image-c}
```

### 6.2 键值

| 键 | 取值 | 说明 |
| --- | --- | --- |
| `h` / `height` | 长度 | 全体图片统一高度 |
| `w` / `width` | 长度 | 全体图片统一宽度 |
| `hA`…`hH` | 长度 | 单张高度（优先于全局） |
| `wA`…`wH` | 长度 | 单张宽度（优先于全局） |
| `keepaspectratio` | `true` / `false` | 同时给 h、w 时是否等比，默认 `true` |
| `capA`…`capH` / `captionA`… | 文字 | 单张标题，显示为“图a 标题” |
| `labelA`…`labelH` | 文字 | 单张引用标记，配合 `\ref` / `\figref` |
| `cap` / `label` | 文字 | `\onepicture` 的简写（等价于 capA / labelA） |
| `numstyle` | `letter` / `chinese` | 编号样式，默认 `letter` |
| `align` | `center` / `left` / `right` | 每行的对齐方式，默认 `center` |
| `showlabel` | `true` / `false` | 是否显示编号 / 标题行，默认 `true` |
| `showprefix` | `true` / `false` | 编号行是否带“图a”前缀，默认 `true`（`false` 时只显示标题文字） |
| `gap` | 长度 | 同行图片水平间距，默认 `1em` |
| `vgap` | 长度 | 行间距，默认 `0.5em` |

### 6.3 自动排布算法

- 每张图先按实际宽度测量，再决定每行放几张；
- 三图：在所有“两图同行 + 一图单独”且都放得下的方案中，取两行宽度最均衡者
  （最小化 `max(两图行宽, 单图宽)`）。因此很宽的一张会自然单独成行、较窄的两张
  并排；较宽的一行排在上面。注意两张图的组合按实际下标计算，`(A,C)` 这类非连续
  组合同样正确。
- 其它张数：枚举所有可行的列数，先取“行数最少”，行数相同再取“最长行最短”
  （各行宽度更均衡）。例如 4 张倾向 2+2、5 张 3+2、6 张 3+3、8 张 4+4，而不是
  把首行挤满、留下一个孤零零的尾行；
- 兜底：都放不下时每行一张。

### 6.4 编号与引用

- `numstyle=letter`：图a、图b、图c…
- `numstyle=chinese`：图甲、图乙、图丙…
- `\ref{key}` 只输出编号（a / 甲）；`\figref{key}` 输出“图a / 图甲”。
- `showlabel=false` 时编号行不显示，但 `\label` 仍在盒子外发出，引用依然有效。
- `showprefix=false` 时编号行只显示标题文字（如“初始状态”）；若某图没有标题，
  则整行不显示。

---

## 7. 答案与解析命令

| 命令 | 说明 |
| --- | --- |
| `\tkanswer[宽度]{答案}` | 填空题答案：下划线空线，`answer_shown=true` 时显示答案 |
| `\xzanswer{A}` | 选择题答案括号：显示 `( A )` |
| `\drawpicanswer{原图}{答案图}` | 作图 / 连线题：按答案开关切换显示 |
| `\memoanswer{内容}` | 题目详解（带底纹的 `tcolorbox`） |
| `\jdanswer{内容}` | 小问答案；自动把 `enumerate` 转为内联编号 |
| `\jdanswer*{内容}` | 同 `\jdanswer`，但保留普通 `enumerate` 排版 |

在 `beamer` 中，上述答案默认在第二张 overlay 显示（`\only<2>`）。

---

## 8. 与 beamer 配合

宏包会自动识别 `beamer` 与 `book` 文档类：

- `beamer`：答案高亮用 `\only<2>` 分步显示；`\jdanswer` 等也如此。
- `book`（含 `ctexbook`）：答案直接显示。
- 其它文档类：按 book 方式处理，并输出一条提示信息。

> **注意：不要在 frame 里再写 `\pause`。** 答案的显示已由宏包用 overlay 控制
> （第 1 步题干、第 2 步答案）。额外的 `\pause` 会打乱 overlay 编号，使 `\only<2>`
> 不再匹配，导致答案不显示（或题干被拆成多步）。

---

## 9. 常见问题

**Q：图片显示不出来？**
A：确认图片文件名 / 路径正确；示例使用 `mwe` 提供的 `example-image-a` 等。
若发行版没有该图片，请替换为自己的文件。

**Q：引用显示“图??”？**
A：LaTeX 需要编译两遍才能解析 `\ref`，请连续运行两次 XeLaTeX。

**Q：`numstyle`、`align` 或未知键报错？**
A：`numstyle` 只接受 `letter` / `chinese`，`align` 只接受 `center` / `left` /
`right`；其它键名拼写错误会报 *Unknown key*。

**Q：选项里有逗号会出错吗？**
A：不会。选项在传入前已被花括号包裹，`l3clist` 会保护其中的逗号。

**Q：某张图比版心还宽？**
A：排版算法无法解决，该图会溢出。请自行设置较小的 `w`。
