# textfix —— 文档共性问题正则处理模块

`tools/textfix/` 是一个**独立的正则文本处理模块**，用于批量修正各卷高考真题
LaTeX 文档（及各卷 `TikZ/*.tex`）中的**共性问题**。规则集中定义、可测试、可扩展；
默认只报告不修改，确认后再 `--write` 写回。

对应 `LaTeX_format_ReadMe.md` 第 21～23 条（全角/半角冒号、行内公式连字符、
`\dfrac`/`\frac`）。

## 目录结构

```
tools/textfix/
├── __init__.py         # 包入口，导出公共 API
├── rules.py            # 正则规则库（Rule 列表）
├── textfix.py          # 核心处理 + 命令行入口
├── test_textfix.py     # 单元测试
├── fixtures/           # 测试用的“修正前 / 修正后”样例文档
│   ├── sample_before.tex
│   └── sample_after.tex
└── README.md
```

## 现有规则

| 规则名 | 说明 | 示例 |
| :--- | :--- | :--- |
| `digit-colon-digit` | 数字之间的全角冒号“：”改为半角冒号“:”（时间、比例等） | `8：00` → `8:00`；`19：26、12：21` → `19:26、12:21` |
| `math-hyphen-merge` | 相邻行内公式之间的连字符并入公式 | `$x$-$t$` → `$x-t$`；`$a$-$b$-$c$` → `$a-b-c$` |
| `dfrac-to-frac` | 分数统一用 `\frac`（行间会自动放大） | `\dfrac{3}{2}` → `\frac{3}{2}` |

> 规则很“窄”：
> - `digit-colon-digit` 仅当冒号**两侧都是数字**时才替换，中文语境中的冒号
>   （如“注意：”“时间是：8 点”）保持不变；
> - `math-hyphen-merge` 仅命中 `$…$-$…$` 形式，`$x$ 与 $t$`、`$-5$`、
>   `$a$-b`、中文连字符等保持不变；
> - `dfrac-to-frac` 只替换命令 `\dfrac` 本身，`\tfrac`、`\frac` 及 `{...}`
>   内容保持不变。

## 命令行用法

在项目根目录执行：

```bash
# 仅检查（默认）：列出待修正的文件、行号与命中片段
python3 tools/textfix/textfix.py 试卷/

# 就地修正
python3 tools/textfix/textfix.py --write 试卷/

# 只处理 .tex 文件（--ext 可重复）
python3 tools/textfix/textfix.py --write --ext .tex 试卷/

# 检查模式：存在待修正处时返回退出码 1（可接入 CI / make check）
python3 tools/textfix/textfix.py --check 试卷/
```

- `<路径>` 可为文件或目录，目录会递归处理；
- 默认扩展名：`.tex` `.sty` `.cls` `.md`（用 `--ext` 覆盖）；
- 默认只报告不修改，`--write` 才写回文件。

> 建议只对文档目录（如 `试卷/`）运行。本 README 与本项目根目录
> `LaTeX_format_ReadMe.md`、`高考物理真题制作规范.md` 的规则表中含有“修正前”
> 示例（如 `$x$-$t$`），请勿对它们执行 `--write`，以免示例被改写。
> 各卷目录内的 `make check` 已内置对本卷 `.tex` 的 `--check`。

## 运行测试

```bash
python3 tools/textfix/test_textfix.py
# 或
python3 -m unittest tools.textfix.test_textfix
# 或（根目录 make tools-test 已包含）
```

测试覆盖：

1. **应命中**：
   - `digit-colon-digit`：时间（`8：00`）、多段（`19：26、12：21`）、
     时分秒（`8：00：00`）、比例（`1：2`）、行内数学模式（`$t=8：00$`）、
     同一句中文冒号 + 数字冒号混排；
   - `math-hyphen-merge`：`$x$-$t$`、`$v$-$t$`、链式 `$a$-$b$-$c$`、
     同一行多组、`$x$-$t$图像`（连字符后无空格）；
   - `dfrac-to-frac`：`\dfrac{3}{2}`、含分式公式、同一行多个、命令后带空格；
2. **不应命中**：中文冒号（`注意：`）、中文冒号后接数字（`时间是：8`）、
   数字后接中文冒号（`8：上课`）、纯 LaTeX 命令（`\tkanswer{√}`）、
   `$x$ 与 $t$`（无连字符）、`$-5$`（前导负号）、`$a$-b`（连字符后接文本）、
   跨行 `$x$\n-$t$`、`\tfrac`、`\dfracX`、`\frac`；
3. 替换计数、幂等性（修正后再次运行不再改动）；
4. 文件级处理（写回 / 不写回 / 目录展开）；
5. **端到端**：`fixtures/sample_before.tex` 经处理必须逐字等于
   `fixtures/sample_after.tex`，且 `sample_after.tex` 再处理保持不变；
6. 规则注册表（名称唯一、正则可 `subn`）。

## 新增规则

在 `rules.py` 的 `RULES` 列表中追加一条 `Rule`：

```python
Rule(
    name="my-rule",                 # 唯一名称
    description="……",               # 说明（会出现在 README / 报告中）
    pattern=re.compile(r"……"),      # Python re 语法
    replacement="……",               # 或可调用对象 f(match) -> str
)
```

然后在 `test_textfix.py` 中补充对应测试，并按需扩展 `fixtures/`；
命令行与测试会自动使用新规则。
