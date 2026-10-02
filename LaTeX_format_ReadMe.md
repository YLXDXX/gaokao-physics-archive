# LaTeX文档格式基本要求

本文件规定 `gaokao-physics-archive`（高考物理真题 LaTeX 档案库）中各份试卷
LaTeX 文档的**基本格式要求**，是后续大量真题转换与人工校对的共同依据。

> 定位：本文是**排版细则**。**文档结构、元数据字段、图片命名与引用标签**等
> 见 `高考物理真题制作规范.md`；**PDF→Markdown 多引擎交叉验证与图片提取**见
> `材料处理与OCR规范.md`；**选项 / 多图 / 答案解析命令**的完整键值见
> `ChoiceQuestion-manual.md`。三份文档与本文配套使用。

---

1. **文档骨架（去中心化）**：每份卷一个独立、可编译目录 `试卷/<年份>/<地区>/`，
   主文件 `<地区>.tex`，固定骨架：

    ```latex
    \ifdefined\gkver\else\def\gkver{student}\fi
    \documentclass[\gkver]{gaokaozhenti}
    \begin{document}

    \chapter{<年份>年<地区>}

    \begin{enumerate}
    \item
    ...
    \end{enumerate}

    \end{document}
    ```

    - 文档类 `gaokaozhenti.cls` 已统一加载 `PhyUnit`、`ChoiceQuestion`、`enumitem`、
      `mhchem` 等，正文**无需再 `\usepackage`**；
    - 章标题固定为 `\chapter{<年份>年<地区>}`（如 `\chapter{2025年湖北}`）；
    - **整卷所有题目**装在**一个**顶层 `enumerate` 中，一道大题一个 `\item`；
    - 列表序号一律**自动生成**，不得手写编号（实验步骤用 `steps` 环境，见第 20 条）。

2. **学生版 / 教师版两版（必须）**：同一 `.tex` 源文件由 `\gkver` 开关切换，
   **无需改源文件**：

    - 源文件顶部固定两行（见第 1 条）：默认 `student`；
    - 版本差异由 `gaokaozhenti.cls` 依据 `\gkver` 自动设置 `ChoiceQuestion` 的
      `answer_shown`：
      - **学生版**（`answer_shown=false`）：`\xzanswer` 显示空括号“（ ）”、
        `\tkanswer` 显示空线、`\jdanswer` 与 `\memoanswer` **整段不显示**；
      - **教师版**（`answer_shown=true`）：答案高亮显示，`\memoanswer` 详解随答案显示。
    - 命令行切换（各卷目录 `Makefile` 已封装）：

      ```bash
      make student        # 仅学生版 → <地区>_学生版.pdf
      make teacher        # 仅教师版 → <地区>_教师版.pdf
      make / make all     # 两版都生成（TikZ 图片 + 学生版 + 教师版）
      ```

      教师版等价于 `latexmk ... -usepretex='\def\gkver{teacher}'`。
    - **答案侧内容（答案、详解、答案图）只进教师版**；源文中答案命令照常书写即可，
      由宏包按 `answer_shown` 自动显隐，**不要手工注释掉答案**。
    - 学生版面向自测 / 练习；教师版面向讲评。两版共用同一题干与配图，仅答案侧不同。

3. **元数据块（必填，固定字段与顺序）**：每道题在 `\item` 之后、题干之前放置来自
   JSON 的元数据注释块，**13 项齐全、顺序不可变**（便于反向提取回 JSON）：

    ```latex
    \item
    %% number: 4
    %% paperName: 2025年湖北高考第 4 题 4 分
    %% typeId: 1
    %% type: 单选题
    %% chapter: 磁场
    %% point: 磁场的叠加
    %% method: 无
    %% score: 4
    %% degree: 650
    %% duplicateId: 0
    %% body:
    <题干（选择题含选项命令）>

    %% answer: A
    %% memo:
    \memoanswer{……}
    ```

    - 字段含义与来源见 `高考物理真题制作规范.md` 第三节；
    - **无详解时 `%% memo:` 行仍要保留**；
    - `tools/check_paper.py` 会校验字段缺失与顺序。

4. **选择题**：题干 + 配图（置于题干与选项之间）+ `\fourchoices[answer=X]{…}`；
   题干末尾用 `\xzanswer{X}` 保留“（ ）”答案括号习惯。选择题答案**同时**写在
   `\xzanswer{}` 与 `\fourchoices[answer=…]` 两处。

5. **实验题 / 计算题 / 简答题**：题干（+ 配图，一般置于题末、`align=right`）+
   小问用**嵌套 `enumerate`**；小问编号自动生成：

    ```latex
    \begin{enumerate}
    	\item
    	求……；
    	\item
    	求……。
    \end{enumerate}
    ```

6. **答案命令的选用**：

    | 场景 | 命令 |
    | :--- | :--- |
    | 选择题答案括号 | `\xzanswer{AB}` |
    | 划线填空（含实验题中答案为字母组合的填空） | `\tkanswer[宽度]{答案}` |
    | 多小问答案 | `\jdanswer{ \begin{enumerate} … \end{enumerate} }` |
    | 作图 / 连线题 | `\drawpicanswer{原图}{答案图}` |
    | 题目详解 | `\memoanswer{…}`（可多条，作者补充用 `\memoanswer[作者]{…}`） |

    - **答案侧（`\xzanswer`/`\tkanswer`/`\jdanswer`/`\memoanswer`）由 `answer_shown`
      开关统一显隐**（见第 2 条），学生版不出现；
    - `\jdanswer` 会把 `enumerate` 渲染为**内联编号**，故**小问答案必须用 `enumerate`
      与小问一一对应**（保持自动编号）；`\jdanswer*` 则保留普通 `enumerate` 排版；
    - 每道题**必须有一条不带作者名的基本详解 `\memoanswer{}`**；`\memoanswer[作者]{}`
      只作补充、**不能替代**基本详解（基本详解在前、作者注解在后）。

7. **题目详解（`\memoanswer`，必须）**：详解内容**完整取自 `merged.md` 中该题对应的
   “解析/详解”**（不概括、不增删推理步骤），并做 LaTeX 化：数学用 `$…$`、分数用
   `\frac`、单位用 PhyUnit（`\Um`/`\Ums`/`\Umsq`/`\Ukmh` 等）。

    - **解析中的图（必须）**：`merged.md` 解析部分的图（`<img src=…>`，或解析文字
      “如图所示/图 1”等所指的图）**必须随详解一并收录**于 `\memoanswer{…}` 内
      （教师版显示、学生版自动隐藏）；仅最简单的示意图用 TikZ 复刻，复杂/实物图用原图；
      **不得出现解析“引图而图不在”**。解析图命名与存放见 `高考物理真题制作规范.md`。

8. **小问与答案的对应**：题目中有小问（计算题、实验题、探究等）时，小问一律使用
   `enumerate` 编号，答案也使用对应的 `enumerate`（放在 `\jdanswer{}` 内）；
   **切勿把答案放错位置、错配小问**。

9. **来源注释（可选，人工溯源）**：本项目的**机器可读来源**是第 3 条元数据块；
   若人工另需在题干旁标注溯源，可在题前以注释形式记录（不参与排版、正文不出现）。
   **原题题干若带出版 / 考试标注**（如“（2026·××期中）”），录入时一律删除。

10. **图片位置**：选择题配图一律放在**题干与选项之间**；大题配图一律放在**题目最后**
    并靠页面右边（`align=right`）。

11. **整体一致性**：中英文之间要有空格；物理单位用 `PhyUnit` 宏包输入，单位与数字间
    留空格；选择题选项一律用 `ChoiceQuestion` 的选项命令并填答案；划线填空用
    `\tkanswer`；有序列表用 `enumerate`、无序列表用 `itemize`；题干或内容中**成组并列
    的要点**（如“（1）…（2）…（3）…”）应改用列表呈现，不写成一段连续文字；每页开头
    不孤行、每段结尾不孤字；各级标题上下间距受控；图片标题、行间公式、表格标题
    **自动计数**并可用超链接引用；公式引用与文献引用生成超链接；证明要有结尾符号。

    - **单位一律用 `PhyUnit` 宏**（`\Um`/`\Ums`/`\Umsq`/`\UeV`/`\UO` …），**正文禁止裸写单位**。
    - **若所需单位尚未在 `PhyUnit.sty` 中定义，可自行新增**：命令名按「`\U` + 单位符号
      （去空格、前缀并入）」命名（如 `keV → \UkeV`、`GeV → \UGeV`、`THz → \UTHZ`），
      统一写作 `\NewDocumentCommand \Uxxx {O{}} {\__phyunit_space:n{#1} \mathrm{...}}`，
      并在**行末写注释**「类别：符号 中文全称」（如 `% 能量：keV 千电子伏特`）。
      新增请追加到 `PhyUnit.sty` 末尾或同类单位之后，并遵守其文件头的「新增单位规范」。

12. **公式**：公式**不能用图片粘贴**；行间公式与行内公式要区分；行间图形符号居中
    （上下基线对齐）。

13. **化学式、核反应方程、元素符号**：不能放在公式环境中，统一用 `mhchem` 宏包的
    `\ce{...}` 输入（如 `\ce{^18_9 F}`、`\ce{^18_9 F -> X + ^0_1e + ^0_0 \nu}`）。

14. **作图题 / 连线题**（常见于实验题）：用 `ChoiceQuestion.sty` 的
    `\drawpicanswer{原图}{答案图}` 排版——显示答案时在原作图位置切换为答案图；
    两个参数**怎么用图片插入命令就怎么用**，`\drawpicanswer` 仅起显隐作用。

15. **图片编号**：`甲乙丙丁` 等图片编号**不能连在一起**，须逐张拆分，编号由宏
    **自动生成**、引用用 `\ref` 生成超链接。项目默认
    `pic_numstyle=letter, pic_labelprefix=图`（得“图a、图b、图c…”）；需要“甲、乙、丙”
    或“图1、图2”时用命令级 `numstyle=chinese` / `numstyle=arabic` 配合 `labelprefix`。

16. **图片选项**：四个选项为四张图片时，**每个选项一张图片**，不得拼成一张或两张；
    选择题号 `ABCD` **不能画在图中**，由宏自动生成。用
    `\fourchoices[answer=X, ispicture=true, h=2.74cm]{…}{…}{…}{…}`。

17. **自动编号**：所有标题序号、有序列表序号、图片编号、表格 / 公式计数等都**自动
    生成**，不能手动编号（实验步骤用 `steps` 环境，见第 20 条）。

18. **图片排版命令（统一用 ChoiceQuestion）**：`hxfigs` 不再提供多图命令。

    - **单图**：`\onepicture[w=<cm>]{图}`（`\onepicture` 默认 `showlabel=false`，不需编号；
      确需编号用 `num=`/`showlabel=true`）；
    - **多图**：`\twopicture` … `\ninepicture[<键>]{图1}…{图n}`，同一题干多幅图**优先排成
      一行**，放不下自动折行；
    - **图片选项**：`\fourchoices[ispicture=true, …]`；
    - 尺寸键：`w`/`width`、`h`/`height` 统一尺寸，`wA..wI`/`hA..hI` 单图尺寸（**绝对 cm**）；
      `scale`/`s` 为缩放倍数（无单位，仅对 `\includegraphics`/`\includesvg` 生效）；
      同时给宽高时默认 `keepaspectratio` 等比缩放（不变形）；
    - `align`/`al`（`left|center|right`，简写 `l|c|r`）控制对齐；`showlabel`/`showprefix`/
      `gap`/`vgap`/`topsep`/`bottomsep` 控制编号与间距；
    - **SVG 图**用 `\includesvg{figs/03}`（不带扩展名，需 `svg` 宏包与 shell-escape）；
      **位图**直接写 `figs/03.png` 或纯文件名；
    - 完整键值见 `ChoiceQuestion-manual.md` 第 5–6 节。

19. **去标签后须补回编号**：来源图中的 `甲乙丙丁` 图号须先去掉（见
    `材料处理与OCR规范.md` 第五节），再由宏自动编号。多图由 `\twopicture…` 自动编号；
    **`\onepicture` 默认 `showlabel=false`**——若文中出现“图甲/图乙（如图所示）”，
    须把该单图写成 `\onepicture[num=甲, …]` **显式补回编号**，保证“引用 ↔ 标签”一致。

20. **列表样式（统一定义在文档类）**：题目为顶层 `enumerate`（标签 `1. 2. 3.`，蓝色）；
    小问为嵌套 `enumerate`（标签 `(1) (2) (3)`）；实验步骤（带圈 ①②③）用 `steps`
    环境（编号自动）：

    ```latex
    \begin{steps}
    	\item
    	平铺白纸，……
    	\item
    	将激光束射入玻璃砖，……
    \end{steps}
    ```

    **禁止**手写 `\item[①]`、`\item[1]` 等编号。

21. **数字之间的时间、比例**：一律使用**半角冒号**“:”，不用全角“：”
    （如 `8:00`、`1:2`）；中文语境中的冒号（如“注意：”）仍用全角。

22. **相邻行内公式之间的连字符并入公式**：写成 `$x-t$`，不写 `$x$-$t$`
    （`$v-t$`、`$a-b-c$` 同理）。

23. **分数统一用 `\frac`**，**不使用 `\dfrac`**（行内、行间均如此，行间公式会自动放大）。

24. **图片尺寸一律用绝对长度 cm**（如 `w=8cm`、`h=5cm`），**不用 `\linewidth` 等相对比例**；
    多图命令的 `w`/`h`/`wA..wI`/`hA..hI` 同理。图片一律**等比缩放**，不得拉伸变形。
    对齐用图片命令的 `align=` 键。

25. **图片取舍（TikZ vs 原图）**：**仅最简单的示意图**（单一坐标轴上的直线/抛物线、
    单个几何关系、纸带等，元素少、一次就能画准）才用 TikZ 绘制；**稍复杂图形**（多要素、
    多标注刻度、多子图、透视、实物简笔等）与实物图、照片**一律用原图**；宁可多用原图，
    不用不准确的 TikZ 简图代替。**原题中的图一律不能漏掉**。**严禁在转换中引入 TikZ
    重绘**——确需重绘者由人工查验并手绘（见第 29 条）。

26. **图片来源**：**文字版 PDF 一律用 `pdf_extract_images.py`（`pdfimages -all`）无损提取的
    内嵌图**；**单图直接取用**；**多子图**（甲乙丙丁、A/B/C/D）用 `recrop_figures.py`
    逐张裁剪回填 `figs/`（调用 `splitpicture`），**裁剪一张核对一张**，不做批量自动裁剪；
    **纯矢量页**（`pdfimages -list` 为 0）用 `pdftoppm -r 600` 渲染后再裁。详见
    `材料处理与OCR规范.md` 第五节。

27. **图片文件命名（短名：题号 + 子图字母）**：图片放在**本卷** `figs/` 下，文件名只含
    题号与子图字母（目录已含年份/地区）：题号两位补零（`01`…`09`），子图字母按阅读顺序
    `a/b/c/…`；解析用图加后缀 `_an`（多张用 `_an1/_an2`）。例：

    ```
    figs/01.svg      % 第 1 题（单图）
    figs/03a.svg     % 第 3 题子图 a
    figs/10b.png     % 第 10 题子图 b
    figs/14_an.jpg   % 第 14 题解析用图（答案侧）
    ```

28. **引用标签（统一格式：年份 + 地区 + 题号 + 子图字母）**：凡在题干 / 小问中引用配图，
    使用统一标签 `YYYY地区QQx`（如 `2025湖北10a`、`2026云南12`）：

    - 多子图：`\twopicture[labelA=2026云南08a, labelB=2026云南08b, labelC=2026云南08c]{…}{…}{…}`；
    - 单图需引用：`\onepicture[num=12, showlabel=false, label=2026云南12, …]{…}`；
    - 正文引用一律用 `\ref{标签}`（显示为图号/子图字母），**不使用 `\subref`**。

29. **TikZ 重绘（人工）“重绘前后”核对**：确需 TikZ 重绘的图，一律写成该卷 `TikZ/` 下的
    **独立图片文档**（`standalone` 文档类，一张图一个 `.tex`），编译为 PDF，正文用
    `\onepicture{TikZ/<名>.pdf}` 引用。**重绘须在本卷 `TikZ/tikz_sources.json` 登记原图**
    （格式见 `tools/README.md`；原图建议随源码入库到 `TikZ/originals/`，确无原题图者写
    `null`），并 `make tikz-compare` 生成 `tikz_compare/<文档>_重绘前后.png`（左＝原图 /
    右＝重绘）**逐张核对**形状、方向、标注、比例；`make check-tikz` 校验登记一致性。

30. **TikZ 坐标图纵横比**：`\begin{tikzpicture}[x=…,y=…]` 中横、纵比例应**分别选取**，
    使整图（含坐标轴与标注）宽高比大致在 **1.2:1 ~ 2:1** 之间；**坐标比例不得过小**，
    务必使轴名、刻度、标注与曲线**不挤在一起**（纵轴轴名置于轴顶并留足纵向空间）；
    应**先定整图目标尺寸再反算比例**。花括号方向：标签在下用 `hxbr`，标签在上用 `hxbrUp`；
    坐标轴标识用 `below right`（纵轴箭头尖端右下方一点），不用 `anchor=south east`。

31. **选项的源文格式：一个选项占一行**。`\fourchoices`（及 `\threechoices` 等）的选项
    参数 `{…}` **每个单独占一行**，命令与可选参数（`[answer=…]`）单独一行，便于人工查看
    与修改；该写法与全部挤在一行等价，输出完全一致。示例：

    ```latex
    \fourchoices[answer=D]
    {$t_3$ 时刻，玩具直升机回到 $t=0$ 时的位置}
    {$t_2$ 时刻，玩具直升机距地面最远}
    {$t_1$ 时刻，玩具直升机的加速度方向发生变化}
    {在 $t_2\sim t_3$ 时间内，玩具直升机一直向上运动}
    ```

32. **段落分行（源文书写，必须）**：各自独立的段落 / 编号条目必须**真正分行**——LaTeX 中
    连续两行只算**一个空格**，不会换行。凡形如 `……变化情况。` 后**紧接**
    `\textbf{2. 两类基本模型}`（编号条目）、或一段结束后紧接另一段，**必须用空行或显式
    `\par` 断开**，否则会挤在同一行。要点：

    - 编号条目 `\textbf{1.}`、`\textbf{2.}`… 各自**另起一段**（行尾加空行或 `\par`）；
    - `\textbf{1. …}` 之后接 `itemize`/`enumerate`、或列表 `\end{…}` 之后接下一段，
      本身已另起段落，无需再加；
    - 同一段内部**不要**为视觉换行随意加 `\par`（会把一段拆成两段）；
    - 自查：检索“。1.”“。2.”“。3.”以及“某行行尾 + 下一行以 `\textbf{` 开头”，
      发现即补空行 / `\par`，再渲染确认。

33. **禁止的旧式图片写法**：不得出现 `\begin{figure}`、`\begin{subfigure}`、`\subref`、
    `\includegraphics{pic/…}`、`tikz/…`（小写旧路径）等；图片一律用第 18 条的
    ChoiceQuestion 命令，图片路径统一 `figs/`（重绘为 `TikZ/`）。`make check` 会检查。

34. **版面微调命令（全项目公用，仅学生版生效）**：排学生版需要“断页 / 撑开 / 留白”时，
    **不要直接用** `\newpage`、`\vfill`、`\vfil`、`\hfill`、`\hfil` 等原生命令，而应使用
    `gaokaozhenti.cls` 提供的**公用微调命令**——它们在**学生版**照常执行、在**教师版自动
    隐藏**（教师版含答案与详解、版面本就不同，直接使用原生命令会造成教师版大段空白或错位）：

    | 公用命令 | 等价于 | 作用 |
    | :--- | :--- | :--- |
    | `\gknewpage` | `\newpage` | 仅学生版断页 |
    | `\gkvfill` | `\vfill` | 仅学生版纵向撑满 |
    | `\gkvfil` | `\vfil` | 仅学生版纵向撑开（可收缩） |
    | `\gkhfill` | `\hfill` | 仅学生版横向撑满 |
    | `\gkhfil` | `\hfil` | 仅学生版横向撑开（可收缩） |

    - **例外（重要）**：作为**版面结构**必需的命令（如并排两个 `minipage` 之间的 `\hfill`）
      仍用**原生** `\hfill`——否则教师版会错位；只有“纯微调”才用公用命令。
    - `tools/check_layout_cmds.py`（`make check` 已接入）会检查原生 `\newpage`/`\clearpage`/
      `\vfill`/`\vfil`/`\hfil`（不检查 `\hfill`，以免误伤 `minipage` 结构）。

---

> **自动化检查**：
> - 第 21～23 条（数字间全角冒号、行内公式连字符/en-dash、`\dfrac`）可用
>   `python3 tools/textfix/textfix.py --check 试卷/`（详见 `tools/textfix/README.md`）；
> - 第 11、12、32 条与数学模式内 CJK（裸单位、图片充当公式、段落分行、`\mathrm{汉字}`）可用
>   `python3 tools/check_content.py 试卷/`；
> - 第 1～4、15、28、33 条（骨架/两版/元数据/图片命令/标签）可用
>   `python3 tools/check_paper.py 试卷/`；
> - 第 34 条（原生版面命令）可用 `python3 tools/check_layout_cmds.py 试卷/`；
> - 编译日志**缺字**（`\mathrm{汉字}` 丢字）可用 `python3 tools/check_glyphs.py 试卷/`；
> - **成品跨项复查**（解析引图必在、选择题三处答案一致、与 JSON 一致）可用
>   `python3 tools/check_review.py 试卷/`。
> 以上均已接入各卷 `make check`。
>
> **图片处理细则**（来源优先级、复合图拆分、去标签 / 去白边、底稿漂移）见
> `材料处理与OCR规范.md` 第五节与 `高考物理真题制作规范.md` 第五节。
> **ChoiceQuestion 命令的完整键值**见 `ChoiceQuestion-manual.md`。
> 本文与 `高考物理真题制作规范.md`、`材料处理与OCR规范.md` 同为后续批量转换的共同依据。
