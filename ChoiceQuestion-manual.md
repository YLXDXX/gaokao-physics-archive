# ChoiceQuestion.sty 使用说明

版本 0.10 ｜ 面向中文试卷 / 教材（`ctex`、`book` 文档类）的选择题 / 多图 / 答案解析辅助宏包

> **本项目（QJPhysics）扩展**（v0.10，向后兼容）：`\memoanswer` 新增可选项
> `[解析人]`（见第 7 节），可为同一道题的补充解析标注作者；
> 新增 `fig`/`figA…figI` 语义别名、
> **用 `fig`/`fignum` 给出编号时自动生成引用标签**（`pic_reflabelprefix`，默认 `fig:`）、
> 以及**可注册的自定义图片编号样式** `\CQDeclarePicNumStyle`（见第 6.5 节），
> 便于图号与原书一致（如「图 1.1.7」）并用 `\ref` 引用。
> `num`/`numA…` 仍只覆盖显示，不自动生成标签（与 v0.8 行为一致）。

---

## 1. 简介

`ChoiceQuestion` 在 `exam-zh-choices` 提供的选项环境之上封装了：

- 数量固定、写法简洁的选择题命令 `\twochoices` … `\ninechoices`；
- 图片选项的统一 / 单项尺寸控制与自动缩放；
- 多图排版命令 `\onepicture` … `\ninepicture`，按图片实际宽度自动分行
  （三图还会额外尝试非相邻两图配对），并支持标题、编号（字母 / 甲乙丙 / 数字）
  与 `\ref` 引用，以及 `scale` / 宽高尺寸、每行左/中/右对齐
  （`align`/`al`，取值可简写 `c`/`l`/`r`）、上下间距（`topsep`/`bottomsep`）、
  隐藏“图a”前缀、单张编号覆盖（`numA`…`numI` / 单图 `num`，任意文字；
  语义别名 `figA`…`figI` / `fig`）；
  单图命令 `\onepicture` 默认不显示编号（`showlabel=false`），
  但给出 `num`/`numA`…`numI`/`fig`… 时会自动显示编号；其中仅 `fig`/`figA`…
  会**自动生成引用标签**（见 6.5 节）；
  尺寸注入同时适配 `\includegraphics` 与 `svg` 宏包的 `\includesvg`；
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
| `pic_numstyle` | `letter` / `chinese` / `arabic`，或自定义样式名 | 多图编号的**全局默认**样式，默认 `letter`（命令级 `numstyle` 可覆盖；自定义样式见 6.5） |
| `pic_labelprefix` | 文字 | 多图编号的**全局默认**前缀，默认 `图`；置空 `{}` 得裸编号（甲/乙/丙…） |
| `pic_reflabelprefix` | 文字 | 用 `fig`/`fignum` 给出编号而未给 `label` 时，**自动生成引用标签**的前缀，默认 `fig:`（如 `fig=1.1.7` → `label=fig:1.1.7`）；`num`/`numA…` 不触发自动标签 |

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
| `scale` / `s` | 数字 | 所有选项统一缩放倍数（无单位，如 `scale=1.4`） |
| `hA`…`hI` | 长度 | 第 1~9 项单独高度（优先于全局） |
| `wA`…`wI` | 长度 | 第 1~9 项单独宽度（优先于全局） |
| `scaleA`…`scaleI` / `sA`…`sI` | 数字 | 第 1~9 项单独缩放倍数（优先于全局） |
| `keepaspectratio` | `true` / `false` | 同时给 h、w 时是否等比，默认 `true` |

选项内容处理规则：

1. 纯文件名（不含控制序列）→ 自动包裹 `\includegraphics[尺寸]{文件}`；
2. 已含 `\includegraphics` 或 `svg` 宏包的 `\includesvg` → 把尺寸（含 `scale`）注入其可选参数（放在最前，用户显式参数可覆盖）；
3. 其它内容（`\rule`、`tikz` 等）→ 用 `\resizebox` 按 h/w 缩放（`scale` 仅对 `\includegraphics`/`\includesvg` 生效）。

---

## 6. 多图命令

### 6.1 命令一览

`\onepicture` … `\ninepicture`，第 n 个命令接受 n 个必选参数
（图片文件名、`\includegraphics` / `\includesvg` 或任意内容）。内容处理规则与
图片选项相同：纯文件名自动包裹 `\includegraphics`，已含 `\includegraphics` /
`\includesvg` 则注入尺寸，其它内容用 `\resizebox` 缩放（见 5.3 节）。

**`\onepicture` 默认 `showlabel=false`**（单图通常不需要编号 / 标题行），
因此大量单图可直接写 `\onepicture[w=…]{图}`；确需编号 / 标题时用 `showlabel=true`。
其余多图命令 `\twopicture` … `\ninepicture` 默认 `showlabel=true`。
**例外**：只要给出编号覆盖 `num`/`numA`…`numI`（或 `fig`/`figA`…），
就自动开启编号行，无需再写 `showlabel=true`（详见 6.4 节）。

```latex
\onepicture[w=6cm]{example-image-a}                    % 单图，不显示编号
\onepicture[num=丙, w=6cm]{example-image-c}            % 给出编号 → 自动显示“图丙”
\threepicture[w=3cm, capA=甲, capB=乙, capC=丙]        % 多图，自动 甲乙丙
  {example-image-a}{example-image-b}{example-image-c}
```

### 6.2 键值

| 键 | 取值 | 说明 |
| --- | --- | --- |
| `h` / `height` | 长度 | 全体图片统一高度 |
| `w` / `width` | 长度 | 全体图片统一宽度 |
| `scale` / `s` | 数字 | 全体图片统一缩放倍数（无单位，如 `scale=1.4`；仅对 `\includegraphics` / `\includesvg` 生效） |
| `hA`…`hI` | 长度 | 单张高度（优先于全局） |
| `wA`…`wI` | 长度 | 单张宽度（优先于全局） |
| `scaleA`…`scaleI` / `sA`…`sI` | 数字 | 单张缩放倍数（优先于全局） |
| `keepaspectratio` | `true` / `false` | 同时给 h、w 时是否等比，默认 `true` |
| `capA`…`capI` / `captionA`… | 文字 | 单张标题，显示为“图a 标题” |
| `labelA`…`labelI` | 文字 | 单张引用标记，配合 `\ref` |
| `numA`…`numI` / `num` | 文字 | 单张**编号覆盖**（**任意文字**：`numA=丙` / `numA=c` / `numA=3` / `numA={图3}` 均可；默认自动编号），并**自动开启编号行**。用于“图甲乙丙不在一张内嵌图、须分别标注”的实验题；`num` 为 `\onepicture` 的简写（等价 `numA`）。**只改显示，不自动生成引用标签**（需引用请另写 `label` 或用 `fig`） |
| `figA`…`figI` / `fig`（同 `fignum`） | 文字 | 等价于 `numA`…/`num`（**语义别名**），并额外**自动生成引用标签** `pic_reflabelprefix` + 该文字（默认 `fig:`），故 `fig=1.1.7` 既显示「图 1.1.7」，又可用 `\ref{fig:1.1.7}` 引用 |
| `cap` / `label` | 文字 | `\onepicture` 的简写（等价于 capA / labelA） |
| `numstyle` | `letter` / `chinese` / `arabic`，或自定义样式名 | 编号样式，默认 `letter`（可用宏包选项 `pic_numstyle` 改全局默认；自定义样式见 6.5 节） |
| `labelprefix` | 文字 | 编号前缀，默认 `图`；置空 `labelprefix={}` 得裸编号（甲/乙/丙…，可用宏包选项 `pic_labelprefix` 改全局默认） |
| `align` / `al` | `center`/`left`/`right`（简写 `c`/`l`/`r`） | 每行的对齐方式，默认 `center` |
| `showlabel` | `true` / `false` | 是否显示图片下方的编号 / 标题行，默认 `true`（`\onepicture` 默认 `false`；给出 `num`/`numA`…`numI`/`fig`… 时自动开启） |
| `showprefix` | `true` / `false` | 编号行是否带前缀，默认 `true`（`false` 时只显示标题文字） |
| `gap` | 长度 | 同行图片水平间距，默认 `8pt` |
| `vgap` | 长度 | 行间距，默认 `0.5em` |
| `topsep` | 长度 | 图片整体与上方内容的距离，默认 `2pt` |
| `bottomsep` | 长度 | 图片整体与下方内容的距离，默认 `2pt` |

`align` 的键名可简写为 `al`，取值也可用 `c` / `l` / `r`：

```latex
\twopicture[align=left, w=0.2\linewidth]{A}{B}    % 左对齐
\twopicture[al=r,       w=0.2\linewidth]{A}{B}    % 右对齐
\fourpicture[al=c, w=0.3\linewidth]{A}{B}{C}{D}   % 居中（默认）
```

图片整体与上下文之间的距离用 `topsep` / `bottomsep` 控制（默认均为 `2pt`）：

```latex
\twopicture[topsep=6pt, bottomsep=6pt, w=0.3\linewidth]{A}{B}
```

`\includesvg`（`svg` 宏包）与 `\includegraphics` 同样处理：尺寸键会以
`\includesvg[scale=…, width=…]{文件}` 的形式注入（`svg` 宏包需用户自行 `\usepackage{svg}`，
并开启 shell-escape 以便调用 Inkscape 转换）。纯文件名仍按 `\includegraphics` 处理，
不会自动识别 `.svg`：

```latex
\onepicture[w=3cm]{\includesvg{figs/circuit}}          % 注入 width=3cm
\twopicture[scale=0.6]{\includesvg{figs/a}}{\includesvg[height=2cm]{figs/b}}
```

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
- `numstyle=arabic`：图1、图2、图3…（编号为数字）
- `numstyle=<自定义名>`：用 `\CQDeclarePicNumStyle` 注册的任意编号格式（见 6.5 节）
- `labelprefix={}`：裸编号（甲、乙、丙…，不带“图”）。
  例如 `numstyle=arabic, labelprefix={图}` 得“图1、图2、图3…”。
- `\ref{key}` 输出编号（a / 甲 / 1）。
- `showlabel=false` 时编号行不显示，但 `\label` 仍在盒子外发出，引用依然有效。
  `\onepicture` 已默认 `showlabel=false`，单图直接写 `\onepicture[w=…]{图}` 即可。
- `showprefix=false` 时编号行只显示标题文字（如“初始状态”）；若某图没有标题，
  则整行不显示。
- **编号覆盖 `numA`…`numI`（单图 `num`）**：显式指定某张图的编号，覆盖自动编号。
  实验题中“图甲”“图乙”“图丙”常分别来自**多张不同的内嵌图**（不在一张图里），
  排在一起时自动编号会得到“甲乙丙…”，与题号未必一致；此时用编号覆盖即可。
  覆盖值是**字面文字，不做样式换算**，因此中文、字母、数字、甚至含前缀的整串都能写。
  **只要给了编号覆盖就自动开启编号行**，无需再写 `showlabel=true`；但显式写
  `showlabel=false` 仍会隐藏显示（`\ref` 照常有效）。
  ```latex
  % 单图：给编号即自动显示
  \onepicture[num=丙, w=4.2cm]{figs/exp1C.jpg}                      % 显示“图丙”
  \onepicture[labelprefix={}, num=丙, w=4.2cm]{figs/exp1C.jpg}      % 显示“丙”

  % 只想要 \ref 不想显示：显式 showlabel=false
  \onepicture[num=丙, showlabel=false, label=fig:c, w=4.2cm]{x}     % 不显示，\ref=丙

  % 多图：逐张覆盖，未覆盖的仍自动编号
  \twopicture[width=3.4cm, numA=甲, numB=丙]{figs/exp1A.jpg}{figs/exp1C.jpg}    % 图甲 图丙
  \threepicture[numstyle=chinese, labelprefix={}, numB=戊]{a}{b}{c}             % 甲 戊 丙
  ```
  覆盖时 `labelprefix` 仍会加在覆盖串**前面**；默认前缀为 `图`，故 `num=丙` 显示“图丙”。
  想要裸编号“丙”，把 `labelprefix` 置空（`labelprefix={}`）；若覆盖串本身已含“图”，
  则同样先置空 `labelprefix` 以免重复（如 `numA={图3}` + `labelprefix={}` 得“图3”）。
  仅当图本身含义就是“标题”而非“编号”时，才改用 `capA={文字}`。
- **编号样式与覆盖的配合**：未覆盖的图由 `numstyle=letter|chinese|arabic` 决定
  （a–i / 甲–壬 / 1–9），覆盖键只改对应那一张：
  ```latex
  \fourpicture[numstyle=letter, labelprefix={图}]{a}{b}{c}{d}       % 图a 图b 图c 图d（全自动）
  \fourpicture[numstyle=arabic, labelprefix={图},
               numA=3, numB=1, numC=2, numD=4]{a}{b}{c}{d}          % 图3 图1 图2 图4（全覆盖）
  \twopicture[numstyle=chinese, numA=丁, numB=己]{a}{b}             % 图丁 图己
  \twopicture[labelprefix={}, numA={图3}, numB={图5}]{a}{b}         % 图3 图5（整串自带前缀）
  ```
  未被覆盖的图按**位置**自动编号（第 3 张即 3 / 丙 / c），因此覆盖值与自动编号
  可能重复，属正常现象；需要独立序列时把该序列的图逐张覆盖即可。
- **编号覆盖与 `\ref`**：覆盖值同时写入 `\label`，故 `\ref` 与该图下方显示一致：
  ```latex
  \onepicture[labelprefix={}, num=丙, label=fig:C, w=4cm]{x}
  见图\ref{fig:C}。   % 输出“见图丙。”
  ```

---

### 6.5 显式编号、自动引用标签与自定义编号样式

**（1）显式编号 `num` / `fig`（逐图指定编号）**

在需要「编号与原书一致」（如原书图号是 1.1.7、1.1.8……）时，用 `num=`/`fig=` 直接给出编号，
`labelprefix`（默认「图」）会加在其前：

```latex
\onepicture[fig=1.1.7, w=6cm]{figs/fig1_1_07.png}     % 显示「图 1.1.7」
\twopicture[figA=1.1.11, figB=1.1.12, w=5cm]{a}{b}    % 显示「图 1.1.11」「图 1.1.12」
```

`num` 与 `fig` 对**显示**完全等价；区别在于**是否自动生成引用标签**（见下）。

**（2）自动引用标签（仅 `fig`/`fignum`）**

用 `fig`/`fignum`（或多图 `figA…figI`/`fignumA…`）给出编号而**未写 `label`** 时，
宏包自动生成引用标签 `<pic_reflabelprefix><编号>`（默认前缀 `fig:`）。因此可写：

```latex
\onepicture[fig=1.1.7, w=6cm]{figs/fig1_1_07.png}
如图 \ref{fig:1.1.7} 所示 ……    % 编译 →「如图 1.1.7 所示」
```

- `num`/`numA…` 只覆盖显示，**不会**自动生成标签（与 v0.8 兼容）；
  要用 `num` 引用时请显式写 `label`（见 6.4 节）；
- 若显式写了 `label`，则以显式 `label` 为准（自动标签不覆盖）；
- 标签前缀可用宏包选项 `pic_reflabelprefix` 更改（如 `fig:`、`pic:`、`tu:`）；
- 编号值同时写入 `\label`，故 `\ref` 与图下显示**完全一致**。

> 提示：自动标签取自**编号字面值**，因此同一编号不要在不同题目中重复使用，
> 否则会产生 `Label … multiply defined` 警告（`\ref` 取最后一次定义）。

**（3）自定义编号样式 `\CQDeclarePicNumStyle`**

若某书/某类文档需要别的自动编号格式，可注册一个样式名（无需改动宏包源码）：

```latex
% 代码中 #1 = 本次调用内的图片序号（1..9）
\CQDeclarePicNumStyle{book}{\thesection.#1}   % 得「1.1.1、1.1.2…」（章.节.序）
\CQDeclarePicNumStyle{Fig}{\textbf{Fig.}#1}   % 得「Fig.1、Fig.2…」

% 命令级用法
\fourpicture[numstyle=book, labelprefix={图}]{a}{b}{c}{d}
```

- 参数体里用**单个 `#1`**（不是 `##1`）指代图片序号；同名样式可重复声明，后者覆盖前者；
- 内置样式仍为 `letter`/`chinese`/`arabic`；`numstyle` 亦接受 `\CQDeclarePicNumStyle` 注册的名字；
- 自定义样式码里可用任意 LaTeX 命令（`\thesection`、`\arabic{...}`、`\textbf{}` 等），
  从而适配不同教材/试卷的图号习惯；
- 也可设为**全局默认**：样式注册与编号解析是分离的，`\usepackage[pic_numstyle=book]{ChoiceQuestion}`
  之后再在导言区 `\CQDeclarePicNumStyle{book}{…}` 即可生效（注册须发生在实际排版之前）。

---

## 7. 答案与解析命令

| 命令 | 说明 |
| --- | --- |
| `\tkanswer[宽度]{答案}` | 填空题答案：下划线空线，`answer_shown=true` 时显示答案 |
| `\xzanswer{A}` | 选择题答案括号：显示 `( A )` |
| `\drawpicanswer{原图}{答案图}` | 作图 / 连线题：按答案开关切换显示 |
| `\memoanswer{内容}` | 题目详解（带底纹的 `tcolorbox`） |
| `\memoanswer[解析人]{内容}` | 同上，并在详解前显示解析标识 / 解析人名字；不写可选项时行为不变 |
| `\jdanswer{内容}` | 小问答案；自动把 `enumerate` 转为内联编号 |
| `\jdanswer*{内容}` | 同 `\jdanswer`，但保留普通 `enumerate` 排版 |

一道题可以有多份详解：最基本的详解直接用 `\memoanswer{...}`；其他人补充的思路 / 方法可
用可选项标出解析标识、解析人姓名，排版时会在详解正文前显示加粗的 `【解析人】`：

```latex
\memoanswer{这是基本的详解内容。}
\memoanswer[张三]{补充思路：还可以用数形结合处理。}
\memoanswer[李四]{补充方法：李四的做法是先画图再列式。}
```

- 可选项可省略，也可写成空的 `[]`；两者等价，都不会显示任何解析人标识（向后兼容）。
- 可选项与正文的先后顺序任意，一个题目可重复使用任意多次，从而并列展示多份解析。
- 与其它答案命令一致：`answer_shown=false` 时整体不显示；`beamer` 中同样在第二张
  overlay 出现。

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
A：`numstyle` 接受内置的 `letter` / `chinese` / `arabic`，或经
`\CQDeclarePicNumStyle` 注册的样式名；`align` 只接受 `center` /
`left` / `right`（或其简写 `c` / `l` / `r`，键名也可写 `al`）；其它键名拼写错误会报
*Unknown key*。宏包选项 `pic_numstyle` 不校验取值，未知/尚未注册的样式在排版时回退为
`letter`。

**Q：`scale` 与 `w`/`h` 同时给出会怎样？**
A：`scale` 只对 `\includegraphics` / `\includesvg` 生效，且按“注入在前、用户显式在后”
处理；同一张图同时给 `scale` 与 `w`/`h` 时，`w`/`h`（或 `\includegraphics` /
`\includesvg` 里显式写的）优先生效。一般同一张图只用其中一种。

**Q：`\onepicture[num=丙]` 要额外写 `showlabel=true` 吗？**
A：不需要。只要给出 `num`/`numA`…`numI` 就会自动开启编号行，直接显示
“图丙”（`labelprefix={}` 时为裸编号“丙”）。若只想用 `\ref`、不想在图下显示，
可显式写 `showlabel=false`，此时显示被隐藏但引用照常。

**Q：`numA`…`numI` / `num` 与 `numstyle` 是什么关系？**
A：`numstyle` 只决定**自动**编号（a–i / 甲–壬 / 1–9，或自定义样式）；`numX` 是某一张图的
**字面覆盖**，不做样式换算，给什么显示什么（`丙`、`c`、`3`、`{图3}` 均可）。
未被 `numX` 覆盖的图仍按 `numstyle` 自动编号。`num` 是 `\onepicture` 的简写
（等价 `numA`）。`num`/`numA…` 只改显示、**不会**自动生成引用标签；注意显示时
`labelprefix` 仍会加在覆盖值前，默认前缀为 `图`。

**Q：怎样让 `\ref` 直接引用图号？**
A：用语义别名 `fig`/`fignum`（多图 `figA…figI`）给出编号且不写 `label`，宏包会自动
生成标签 `<pic_reflabelprefix><编号>`（默认 `fig:`），如 `fig=1.1.7` 可用
`\ref{fig:1.1.7}` 引用。若用 `num` 或需要自定义标签名，请显式写 `label=…`。

**Q：出现 `Label … multiply defined` 警告？**
A：自动标签来自编号字面值（如 `fig:1.1.7`），同一编号在多处出现即重复定义。
请保证编号唯一，或给重复者显式指定不同的 `label`。用 `num`/`numA…` 覆盖显示不会
产生自动标签，也就不会有此问题。

**Q：`\includesvg` 能用尺寸键吗？**
A：能。选项内容里含 `\includesvg` 时，尺寸键会被注入其可选参数，与
`\includegraphics` 一致。`svg` 宏包需自行加载，并开启 shell-escape 供 Inkscape
转换。纯文件名不会自动按 `.svg` 识别。

**Q：选项里有逗号会出错吗？**
A：不会。选项在传入前已被花括号包裹，`l3clist` 会保护其中的逗号。

**Q：某张图比版心还宽？**
A：排版算法无法解决，该图会溢出。请自行设置较小的 `w`。

---

## 10. 版本与更新日志

当前版本 **0.10**（2026-10-01）。

- **0.10**：`\memoanswer` 新增可选项 `[解析人]`，用于标注补充解析的解析标识 / 解析人姓名；
  不写可选项时行为与旧版一致。
- **0.9**：新增 `fig`/`fignum` 语义别名（多图 `figA…figI`）；用 `fig` 给出编号且未写
  `label` 时，按 `pic_reflabelprefix`（默认 `fig:`）自动生成引用标签；新增
  `\CQDeclarePicNumStyle` 注册自定义编号样式；`pic_numstyle` 宏包选项亦接受自定义样式名；
  `num`/`numA…` 保持只覆盖显示、不自动生成标签（向后兼容）。
- **0.8**：`num`/`numA…` 隐含开启编号行；新增 `\ninepicture`；尺寸注入适配 `\includesvg`。
- **0.7**：单图编号覆盖扩展为 `num`/`numA…numH`（任意文字）。
- **0.6**：多图整体上下间距 `topsep`/`bottomsep`。
- **0.5**：`align` 键名与取值简写（`al`、`c`/`l`/`r`）。
- **0.4**：多图 `scale` / 数字编号 / 编号前缀。
- **0.3**：图片尺寸统一 / 单项覆盖、`keepaspectratio` 等。

> 兼容性：0.10 对 0.9 完全向后兼容；`num`/`numA…` 的行为未变（只改显示，不生成标签）。
