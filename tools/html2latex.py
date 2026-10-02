# -*- coding: utf-8 -*-
"""HTML 片段 → LaTeX 文本转换器（移植自 grabgaokao/texgen/html2latex.py）。

> 本模块用于替换 `json_to_tex.py` 早期粗糙的正则转换；依赖 `beautifulsoup4`。

把抓取下来的题库 JSON 中 body / answer / memo 字段（HTML 标签与 MathJax
LaTeX 公式混合）转换成可直接放进 LaTeX 文档的文本：

- HTML 标签：
  - ``<em>``     → 行内数学模式 ``$...$``（斜体变量），内部按数学模式转换
  - ``<sub>``/``<sup>`` → ``$_{...}$`` / ``$^{...}$``，相邻上下标合并（核素记法）
  - ``<strong>`` → ``\\textbf{...}``
  - ``<u>``      → ``\\CJKunderline{...}``（空白内容给下划线空格）
  - ``<s>``      → ``\\CJKsout{...}``
  - ``<p>``      → 段落（块与块之间空一行）
  - ``<br>``     → ``\\\\``
  - ``<img>``    → ``\\includegraphics{...}``/``\\includesvg{...}``，
    图片放入 ``figure`` 环境；通过 ImageRegistry 按引用顺序改名并去重
  - ``<table>``  → ``tabular``（支持 colspan / rowspan）
  - ``<span>``、``<font>`` 等容器 → 仅递归内部内容
- 公式：MathJax 的 ``\\(...\\)`` → ``$...$``，``\\[...\\]`` → ``\\[...\\]``；
  数学模式内出现的汉字等非 ASCII 字符自动包成 ``\\text{...}``
- 特殊字符：``_ & % # $ ^ ~ \\ { }`` 等做 LaTeX 转义；
  ``－ ＋ ＝ ＜ ＞ ～ ℃ ° × ÷ − μ Ω …`` 等全角/希腊/数学字符
  映射为对应 LaTeX 命令

原则：不加入、不减少原内容，仅做排版格式上的等价转换。
"""

from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

# --------------------------------------------------------------------------
# 字符映射表
# --------------------------------------------------------------------------

# 数学模式内：字符 → LaTeX 命令
MATH_CHAR_MAP = {
    # 全角/变体运算符
    '＝': '=', '﹦': '=', '＋': '+', '﹢': '+', '－': '-', '﹣': '-',
    '＜': '<', '＞': '>', '～': '\\sim', '∶': ':', '︰': ':',
    # 各种连字符/减号
    '−': '-', '–': '-', '—': '-', '‒': '-', '‑': '-', '─': '-',
    # 数学符号
    '×': '\\times', '÷': '\\div', '·': '\\cdot', '⋅': '\\cdot',
    '∙': '\\cdot', '・': '\\cdot', '·': '\\cdot', '…': '\\dots',
    '⋯': '\\cdots', '≈': '\\approx', '≤': '\\le', '≥': '\\ge',
    '≠': '\\neq', '±': '\\pm', '∞': '\\infty', '∈': '\\in',
    '⊂': '\\subset', '⊄': '\\nsubseteq', '∩': '\\cap', '⊗': '\\otimes',
    '∠': '\\angle', '∝': '\\propto', '√': '\\sqrt{\\phantom{1}}',
    '∧': '\\wedge', '∨': '\\vee', '∴': '\\therefore', '∀': '\\forall',
    '∃': '\\exists', '¬': '\\neg', '≡': '\\equiv', '∼': '\\sim',
    '≪': '\\ll', '≫': '\\gg', '∽': '\\backsim', '∥': '\\parallel',
    '⊥': '\\perp', '∟': '\\perp', '︱': '|',
    '→': '\\to', '←': '\\leftarrow', '⇌': '\\rightleftharpoons',
    '⇒': '\\Rightarrow',
    # 角度/单位（^\circ 用 {} 包成独立组，避免与相邻上标合并成 Double superscript）
    '°': '{^\\circ}', 'º': '{^\\circ}', '˚': '{^\\circ}', '℃': '{^\\circ}C',
    '′': "'", '″': "''", 'ʹ': "'", 'ʺ': "''",
    # 希腊字母
    'α': '\\alpha', 'β': '\\beta', 'γ': '\\gamma', 'δ': '\\delta',
    'ε': '\\varepsilon', 'ϵ': '\\epsilon', 'ζ': '\\zeta', 'η': '\\eta',
    'θ': '\\theta', 'ι': '\\iota', 'κ': '\\kappa', 'λ': '\\lambda',
    'μ': '\\mu', 'ν': '\\nu', 'ξ': '\\xi', 'π': '\\pi', 'ρ': '\\rho',
    'σ': '\\sigma', 'τ': '\\tau', 'υ': '\\upsilon', 'φ': '\\varphi',
    'ϕ': '\\phi', 'χ': '\\chi', 'ψ': '\\psi', 'ω': '\\omega',
    'Γ': '\\Gamma', 'Δ': '\\Delta', '∆': '\\Delta', 'Θ': '\\Theta',
    'Λ': '\\Lambda', 'Ξ': '\\Xi', 'Π': '\\Pi', 'Σ': '\\Sigma',
    'Φ': '\\Phi', 'Ψ': '\\Psi', 'Ω': '\\Omega', 'Ω': '\\Omega',
    # 图形符号
    '△': '\\triangle', '○': '\\bigcirc', '●': '\\bullet', '∘': '\\circ',
    '¢': '\\textcent',
    # 物理常量/符号（Fandol 无字形，转标准 LaTeX 命令）
    'ℏ': '\\hbar', '⊙': '\\odot', 'ȧ': '\\dot{a}',
    # 制表符/形状符号
    '┤': '\\dashv', '匸': '\\sqcup',
    # 同形字/字形变体归一化（源站录入编码错误，视觉/语义相同）：
    # 西里尔同形字 → 拉丁（数学斜体字母见下方 _MATH_ITALIC；
    # 日文新字体/繁体见 _CJK_HOMOGLYPHS）
    'Р': 'P', 'О': 'O',
}

# 日文新字体/繁体/异体字 → 简体（源站录入编码错误，Fandol 无对应字形）
_CJK_HOMOGLYPHS = {'圧': '压', '変': '变', '況': '况', '虛': '虚', '圏': '圈',
                   '別': '别', '岀': '出', '靜': '静', '帯': '带'}

# 数学斜体字母（U+1D434–U+1D467）：源站把普通变量写成了数学斜体字符，
# 拉丁字体无这些字形，归一到对应 ASCII 字母（数学模式内本身即斜体）。
_MATH_ITALIC = {}
for _i in range(26):
    _MATH_ITALIC[chr(0x1D434 + _i)] = chr(ord('A') + _i)   # 大写
    _MATH_ITALIC[chr(0x1D44E + _i)] = chr(ord('a') + _i)   # 小写
MATH_CHAR_MAP.update(_MATH_ITALIC)
MATH_CHAR_MAP.update(_CJK_HOMOGLYPHS)

# 带圈数字、罗马数字与拉丁字体缺少的字形：
# - ①-⑩、Ⅰ-Ⅻ：由导言区的 \xeCJKsetcharclass 声明交给 CJK 字体（Fandol）渲染，
#   这里不做转换、保留原字符；
# - ⑪-⑳、ⅰ-ⅻ、⑴-⒇：Fandol 也没有这些字形，仍需转换。
_CIRCLED_DIGITS = {chr(0x2460 + i): f'\\text{{\\textcircled{{{i + 1}}}}}'
                   for i in range(10, 20)}            # ⑪-⑳
_PAREN_DIGITS = {chr(0x2474 + i): f'\\text{{（{i + 1}）}}'
                 for i in range(20)}                  # ⑴-⒇
_ROMAN_LOWER = {'ⅰ': 'i', 'ⅱ': 'ii', 'ⅲ': 'iii', 'ⅳ': 'iv', 'ⅴ': 'v',
                'ⅵ': 'vi', 'ⅶ': 'vii', 'ⅷ': 'viii', 'ⅸ': 'ix', 'ⅹ': 'x',
                'ⅺ': 'xi', 'ⅻ': 'xii'}
MATH_CHAR_MAP.update(_CIRCLED_DIGITS)
MATH_CHAR_MAP.update(_PAREN_DIGITS)
MATH_CHAR_MAP.update({k: '\\text{' + v + '}' for k, v in _ROMAN_LOWER.items()})

# 文本模式内：字符 → LaTeX（注意值里已经包好 $...$）
TEXT_CHAR_MAP = {
    '＝': '$=$', '＋': '$+$', '－': '$-$', '＜': '$<$', '＞': '$>$',
    '～': '$\\sim$', '∶': '$:$',
    '−': '$-$', '–': '$-$', '—': '$-$', '‒': '$-$', '‑': '$-$',
    '─': '$-$', '﹣': '$-$', '﹢': '$+$',
    '×': '$\\times$', '÷': '$\\div$', '·': '$\\cdot$', '⋅': '$\\cdot$',
    '∙': '$\\cdot$', '・': '$\\cdot$', '·': '$\\cdot$',
    '⋯': '$\\cdots$', '…': '$\\ldots$',
    '≈': '$\\approx$', '≤': '$\\leq$', '≥': '$\\geq$', '≠': '$\\neq$',
    '±': '$\\pm$', '∞': '$\\infty$', '∈': '$\\in$', '⊂': '$\\subset$',
    '⊄': '$\\nsubseteq$', '∩': '$\\cap$', '⊗': '$\\otimes$',
    '∠': '$\\angle$', '∝': '$\\propto$', '√': '$\\sqrt{\\phantom{1}}$',
    '∧': '$\\wedge$', '∨': '$\\vee$', '∴': '$\\therefore$',
    '∀': '$\\forall$', '∃': '$\\exists$', '¬': '$\\neg$',
    '≡': '$\\equiv$', '∼': '$\\sim$', '≪': '$\\ll$', '≫': '$\\gg$',
    '∽': '$\\sim$', '∥': '$\\parallel$', '⊥': '$\\perp$', '∟': '$\\perp$',
    '→': '$\\to$', '←': '$\\leftarrow$', '⇌': '$\\rightleftharpoons$',
    '⇒': '$\\Rightarrow$',
    '°': '${^\\circ}$', 'º': '${^\\circ}$', '˚': '${^\\circ}$', '℃': '${^\\circ}C$',
    '′': "$'$", '″': "$''$", 'ʹ': "$'$", 'ʺ': "$''$",
    'α': '$\\alpha$', 'β': '$\\beta$', 'γ': '$\\gamma$', 'δ': '$\\delta$',
    'ε': '$\\varepsilon$', 'ϵ': '$\\epsilon$', 'ζ': '$\\zeta$',
    'η': '$\\eta$', 'θ': '$\\theta$', 'ι': '$\\iota$', 'κ': '$\\kappa$',
    'λ': '$\\lambda$', 'μ': '$\\mu$', 'ν': '$\\nu$', 'ξ': '$\\xi$',
    'π': '$\\pi$', 'ρ': '$\\rho$', 'σ': '$\\sigma$', 'τ': '$\\tau$',
    'υ': '$\\upsilon$', 'φ': '$\\varphi$', 'ϕ': '$\\phi$',
    'χ': '$\\chi$', 'ψ': '$\\psi$', 'ω': '$\\omega$',
    'Γ': '$\\Gamma$', 'Δ': '$\\Delta$', '∆': '$\\Delta$',
    'Θ': '$\\Theta$', 'Λ': '$\\Lambda$', 'Ξ': '$\\Xi$', 'Π': '$\\Pi$',
    'Σ': '$\\Sigma$', 'Φ': '$\\Phi$', 'Ψ': '$\\Psi$', 'Ω': '$\\Omega$',
    'Ω': '$\\Omega$',
    '△': '$\\triangle$', '○': '$\\bigcirc$', '●': '$\\bullet$',
    '∘': '$\\circ$', '¢': '\\textcent{}',
    'ℏ': '$\\hbar$', '⊙': '$\\odot$', 'ȧ': '$\\dot{a}$',
    '┤': '$\\dashv$', '匸': '$\\sqcup$',
    '︰': '$:$', '︱': '$|$', '﹑': '、', '﹐': '，',
    '､': '、', '｡': '。',
    # 同形字/字形变体归一化（源站录入编码错误，视觉/语义相同）：
    # 日文新字体/繁体 → 简体；西里尔同形字 → 拉丁
    'Р': 'P', 'О': 'O',
}
TEXT_CHAR_MAP.update(_CJK_HOMOGLYPHS)
# 数学斜体字母（U+1D434–U+1D467）→ 数学模式变量 $x$（含 svg pdf_tex 补丁）
TEXT_CHAR_MAP.update({k: '$' + v + '$' for k, v in _MATH_ITALIC.items()})
TEXT_CHAR_MAP.update({chr(0x2460 + i): f'\\textcircled{{{i + 1}}}'
                      for i in range(10, 20)})             # ⑪-⑳
TEXT_CHAR_MAP.update({chr(0x2474 + i): f'（{i + 1}）'
                      for i in range(20)})                 # ⑴-⒇
TEXT_CHAR_MAP.update(_ROMAN_LOWER)

# 文本模式需要转义的 ASCII 特殊字符
_TEXT_ESCAPES = [
    ('\\', '\\textbackslash{}'),
    ('{', '\\{'),
    ('}', '\\}'),
    ('_', '\\_'),
    ('&', '\\&'),
    ('%', '\\%'),
    ('#', '\\#'),
    ('$', '\\$'),
    ('^', '\\textasciicircum{}'),
    ('~', '\\textasciitilde{}'),
]

# 数学模式下需要转义的 ASCII 特殊字符（\\ _ ^ { } 是合法数学语法，不转义）；
# 转义逻辑见 _escape_math_specials（需跳过已转义的 \% 等）
_MATH_SPECIAL_CHARS = '&%#$'

# 数学模式下，把非 ASCII 字符包成 \text{...}（需要 amsmath）
_CJK_IN_MATH_RE = re.compile(r'([^\x00-\x7F]+)')

# 数学片段右定界符：容忍源站把 \(...\)/\[...\] 误写成 "\ )"（\ 与 ) 之间多空格）
_MATH_CLOSE_INLINE_RE = re.compile(r'\\\s*\)')
_MATH_CLOSE_DISPLAY_RE = re.compile(r'\\\s*\]')

# 图片最大宽度（pt），超过则等比缩小
_MAX_IMG_WIDTH_PT = 430.0
_PX_TO_PT = 0.75


# --------------------------------------------------------------------------
# 图片注册表：按引用顺序改名（01、02、03……），同一张图片重复引用去重
# --------------------------------------------------------------------------

class ImageRegistry:
    """记录一张试卷中图片的引用顺序，并把本地图片文件按顺序改名为 01.ext …"""

    def __init__(self, json_dir: str):
        # json_dir：JSON 文件所在目录（图片 src 相对它解析）
        self.json_dir = json_dir
        self._map: dict = {}          # src -> 新文件名（无法本地化时为 None）
        self._files: List[Tuple[str, str, str]] = []  # (src, 源绝对路径, 新文件名)

    def register(self, src: str) -> Optional[str]:
        """登记一个图片引用，返回新的文件名（01.png 之类）；无法本地化时返回 None。"""
        src = (src or '').strip()
        if src in self._map:
            return self._map[src]
        name = None
        if src and not src.lower().startswith(('http://', 'https://', 'file://', 'data:')):
            path = os.path.normpath(os.path.join(self.json_dir, src))
            if os.path.isfile(path):
                ext = os.path.splitext(path)[1].lstrip('.').lower()
                if ext == 'gif':
                    # xelatex/graphicx 无法直接包含 gif（无 BoundingBox），
                    # 复制时转成 png，引用名也改为 .png
                    ext = 'png'
                name = f'{len(self._files) + 1:02d}.{ext}'
                self._files.append((src, path, name))
        self._map[src] = name
        return name

    def files(self):
        """返回已登记图片列表 [(src, 源绝对路径, 新文件名), ...]。"""
        return list(self._files)


# --------------------------------------------------------------------------
# 基础转换函数
# --------------------------------------------------------------------------

def _escape_text(s: str) -> str:
    for a, b in _TEXT_ESCAPES:
        s = s.replace(a, b)
    return s


# 私有使用区（Private Use Area，U+E000–U+F8FF）：源站图里的 Wingdings 等
# 图标字体字符（无标准 Unicode 语义、无法用拉丁/中文字体还原），直接删除，
# 避免编译报 Missing character。
_PUA_RE = re.compile('[\ue000-\uf8ff]')


def _strip_pua(s: str) -> str:
    return _PUA_RE.sub('', s)


def text_to_latex(s: str) -> str:
    """纯文本（不在数学模式内）→ LaTeX。"""
    s = _strip_pua(s)
    s = s.replace('\xa0', ' ').replace('\u200b', '').replace('\u3000', ' ')
    s = _escape_text(s)
    for k, v in TEXT_CHAR_MAP.items():
        s = s.replace(k, v)
    return _merge_math_segments(s)


def _escape_math_specials(s: str) -> str:
    """转义数学模式里的 & % # $，但跳过已用反斜杠转义的（如 \\%）。

    MathJax 源码里百分号常写作 ``\\%``，若直接 ``s.replace('%', '\\%')``
    会把 ``\\%`` 变成 ``\\\\%``——LaTeX 里 ``\\\\`` 换行、``%`` 起注释，
    后续内容被注释吞掉、命令参数无法闭合（2001_上海#19 实测）。
    这里按“前面连续反斜杠个数”判断：奇数个 = 已转义，跳过；偶数个（含 0）
    = 裸字符，补一个反斜杠。
    """
    out = []
    escapes = {c: '\\' + c for c in _MATH_SPECIAL_CHARS}
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch in escapes:
            k = 0
            j = i - 1
            while j >= 0 and s[j] == '\\':
                k += 1
                j -= 1
            out.append(ch if k % 2 == 1 else escapes[ch])
        else:
            out.append(ch)
        i += 1
    return ''.join(out)


def math_to_latex(s: str) -> str:
    """数学模式内的文本 → LaTeX（不含 $ 包裹）。"""
    s = _strip_pua(s)
    s = s.replace('\xa0', ' ').replace('\u200b', '')
    out = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        rep = MATH_CHAR_MAP.get(ch)
        if rep is not None:
            out.append(rep)
            # 命令以字母结尾且下一个源字符也是字母/数字时加一个空格，
            # 避免 &beta;g → \betag 这类控制字粘连
            if rep and rep[-1].isalnum() and i + 1 < n and s[i + 1].isalnum():
                out.append(' ')
        else:
            out.append(ch)
        i += 1
    s = ''.join(out)
    # 剩余的非 ASCII（汉字、全角标点等）包成 \text{...}
    s = _CJK_IN_MATH_RE.sub(lambda m: '\\text{' + m.group(1) + '}', s)
    s = _escape_math_specials(s)
    # MathJax 的 \rm{...} 已废弃；\bar 在 \mathrm 内部与 xeCJK 交互会产生
    # U+0016 缺字形（Missing character），这里统一改成 \mathrm / \overline
    # （视觉与语义等价）
    s = s.replace('\\rm{', '\\mathrm{')
    s = s.replace('\\bar', '\\overline')
    return s


def patch_pdftex_text(content: str) -> str:
    """补丁 inkscape --export-latex 生成的 pdf_tex 里的文本。

    pdf_tex 里的文字在 xelatex 下用 Latin 字体排版，希腊字母、带圈数字、
    罗马数字等没有字形（日志报 Missing character），从最终 PDF 里消失。
    这里按 TEXT_CHAR_MAP 的规则把它们换成对应的 LaTeX 命令（与主转换
    程序同一套映射），保证图片文字完整显示。仅替换 Unicode 字符，不动
    pdf_tex 里已有的 LaTeX 命令。
    """
    content = _strip_pua(content)
    content = content.replace('\xa0', ' ').replace('\u200b', '')
    for k, v in TEXT_CHAR_MAP.items():
        content = content.replace(k, v)
    return content


def _at_line_start(out) -> bool:
    """判断当前输出缓冲区是否处于行首（此前为空/只有换行）。

    紧跟图片块等块级内容后的 <br> 会落在行首，此时生成的 \\ 会报
    “There's no line here to end”，应丢弃。
    """
    joined = ''.join(out)
    return not joined.strip() or joined.endswith('\n')


# --------------------------------------------------------------------------
# 主转换器
# --------------------------------------------------------------------------

class HtmlToLatex:
    """把一个 HTML 片段转换成 LaTeX 文本。

    用法：
        conv = HtmlToLatex(images=registry, json_dir='...')
        blocks = conv.convert_blocks(html)      # 返回段落块列表
        text = '\\n\\n'.join(blocks)            # 段落之间空一行
    """

    def __init__(self, images: Optional[ImageRegistry] = None, img_prefix: str = '',
                 img_center: bool = False):
        # img_prefix：图片文件夹名（相对 tex 所在目录），如 2025_湖北
        # img_center：为 True 时图片用 center 环境（答案/解析盒子内不能用
        # figure 浮动体），否则用 figure[htbp] 浮动体
        self.images = images
        self.img_prefix = img_prefix
        self.img_center = img_center
        self._math_open = False       # 是否处于 \( 或 \[ 数学片段中
        self._math_display = False    # 数学片段是否为 \[...\] 显示模式
        self._math_parts: List[str] = []
        self._math_target: Optional[List[str]] = None

    # ---------------- 对外接口 ----------------

    def convert(self, html: str) -> str:
        """把 HTML 片段转换成 LaTeX 文本（段落之间空一行）。"""
        return '\n\n'.join(self.convert_blocks(html))

    def convert_blocks(self, html: str) -> List[str]:
        """把 HTML 片段转换成 LaTeX 段落块列表（不含空块）。"""
        soup = BeautifulSoup(html or '', 'html.parser')
        blocks: List[str] = []
        self._reset_math()
        for child in soup.children:
            self._handle_block_child(child, blocks)
        result = []
        for b in blocks:
            b = _merge_math_segments(b.strip())
            if b.strip():
                result.append(b.strip())
        return result

    # ---------------- 数学片段状态 ----------------

    def _reset_math(self):
        self._math_open = False
        self._math_display = False
        self._math_parts = []
        self._math_target = None

    def _open_math(self, display: bool, target: List[str]):
        self._math_open = True
        self._math_display = display
        self._math_parts = []
        self._math_target = target

    def _flush_math(self) -> str:
        content = ''.join(self._math_parts)
        display = self._math_display
        self._reset_math()
        if display:
            return '\\[' + content + '\\]'
        return '$' + content + '$'

    def _append_math(self, text: str):
        """往数学缓冲区追加内容，并做控制字粘连保护。

        数学内容可能跨 HTML 标签被拆成多段（如 <em>ρ<span>v</span></em> 里
        ρ 与 v 分属两个文本节点），逐段 math_to_latex 后直接拼接会把
        \\rho + v 拼成未定义的 \\rhov。这里在相邻两段之间视情况补空格。
        """
        if self._math_parts and text and text[0].isalnum() \
                and _CONTROL_WORD_END_RE.search(self._math_parts[-1]):
            self._math_parts[-1] += ' '
        self._math_parts.append(text)

    def _append_text(self, s: str, out: List[str]):
        """处理文本模式文本：识别 \\(...\\) 与 \\[...\\] 数学片段。"""
        i, n = 0, len(s)
        while i < n:
            if self._math_open:
                # 右定界符：容忍源站把 \(...\) 误写成 "\ )"（\ 与 ) 之间多空格）
                closer_re = _MATH_CLOSE_DISPLAY_RE if self._math_display else _MATH_CLOSE_INLINE_RE
                m = closer_re.search(s, i)
                if not m:
                    self._append_math(math_to_latex(s[i:]))
                    return
                self._append_math(math_to_latex(s[i:m.start()]))
                out.append(self._flush_math())
                i = m.end()
            else:
                j1 = s.find('\\(', i)
                j2 = s.find('\\[', i)
                candidates = [(j, False) for j in (j1,) if j != -1]
                candidates += [(j, True) for j in (j2,) if j != -1]
                if not candidates:
                    out.append(text_to_latex(s[i:]))
                    return
                j, display = min(candidates)
                out.append(text_to_latex(s[i:j]))
                self._open_math(display, out)
                i = j + 2

    # ---------------- 块级处理 ----------------

    def _handle_block_child(self, node, blocks: List[str]):
        if isinstance(node, Comment):
            # HTML 注释（含 Word 粘贴残留的 <!--[if ...]>...<![endif]--> 条件注释）
            # 不是题目内容，直接丢弃
            return
        if isinstance(node, NavigableString):
            if str(node).strip():
                buf: List[str] = []
                self._append_text(str(node), buf)
                blocks.append(''.join(buf))
            return
        name = (node.name or '').lower()
        if name == 'p':
            buf = []
            self._walk_children(node, 'inline', buf)
            blocks.append(''.join(buf))
        elif name == 'img':
            blocks.append(self._image_block(node))
        elif name == 'table':
            blocks.append(self._table_block(node))
        elif name in ('div', 'body', 'html', 'section', 'article'):
            for c in node.children:
                self._handle_block_child(c, blocks)
        else:
            buf = []
            self._walk_children(node, 'inline', buf)
            blocks.append(''.join(buf))

    # ---------------- 子节点遍历 ----------------

    def _walk_children(self, node, mode: str, out):
        """mode: 'inline'（段落内）、'cell'（表格单元格内）、'math'（数学内）"""
        for child in node.children:
            if isinstance(child, Comment):
                # HTML 注释不是题目内容，直接丢弃
                continue
            if isinstance(child, NavigableString):
                s = str(child)
                if mode == 'math':
                    self._append_math(math_to_latex(s))
                else:
                    self._append_text(s, out)
            else:
                self._handle_tag(child, mode, out)

    def _handle_tag(self, tag: Tag, mode: str, out: List[str]):
        name = (tag.name or '').lower()

        # ---- 数学模式内（mode 为 math，或正处于 \\(...\\) 打开状态）----
        if mode == 'math' or self._math_open:
            if name == 'img':
                if self._math_target is not None:
                    self._math_target.append(self._flush_math())
                    if mode == 'cell':
                        self._math_target.append(self._image_inline(tag))
                    else:
                        self._math_target.append('\n\n' + self._image_block(tag) + '\n\n')
                else:
                    # 数学片段出现在 em/sub/sup 内部（如 <em><img/>N</em>）：
                    # 图片放进数学会编译失败，这里只保留图片引用说明
                    self._append_math('\\;')
            elif name in ('em', 'i', 'b', 'strong', 'span', 'font', 'u', 's', 'p'):
                self._walk_children(tag, 'math', out)
            elif name == 'sub':
                if self._subsup_content(tag):
                    self._append_math(
                        '_{' + _safe_script_content(self._inline_math(tag)) + '}')
            elif name == 'sup':
                if self._subsup_content(tag):
                    self._append_math(
                        '^{' + _safe_script_content(self._inline_math(tag)) + '}')
            elif name == 'br':
                self._append_math(' ')
            else:
                self._walk_children(tag, 'math', out)
            return

        # ---- 图片 ----
        if name == 'img':
            if mode == 'cell':
                out.append(self._image_inline(tag))
            else:
                out.append('\n\n' + self._image_block(tag) + '\n\n')
            return

        # ---- 表格（行内出现的表格）----
        if name == 'table':
            out.append('\n\n' + self._table_block(tag) + '\n\n')
            return

        # ---- 上下标 ----
        if name == 'sub':
            if self._subsup_content(tag):
                out.append('$_{' + _safe_script_content(self._inline_math(tag)) + '}$')
            return
        if name == 'sup':
            if self._subsup_content(tag):
                out.append('$^{' + _safe_script_content(self._inline_math(tag)) + '}$')
            return

        # ---- 斜体（变量）----
        if name == 'em':
            raw = tag.get_text()
            if tag.find('img') is not None:
                # <em> 内含图片（如 <em><img/>N</em>）：图片无法放进数学模式，
                # 整体按普通文本转换（斜体丢失但内容完整保留）
                buf = []
                self._walk_children(tag, 'inline', buf)
                out.append(''.join(buf))
                return
            inner = self._inline_math(tag)
            if not raw.strip():
                out.append(' ')
            elif not re.search(r'[A-Za-z0-9]', raw):
                # 纯中文/标点/空白：按普通文本输出，不加斜体
                out.append(text_to_latex(raw))
            else:
                out.append('$' + inner + '$')
            return

        # ---- 粗体 ----
        if name in ('strong', 'b'):
            buf = []
            self._walk_children(tag, 'inline', buf)
            out.append('\\textbf{' + ''.join(buf) + '}')
            return

        # ---- 下划线（填空）----
        if name == 'u':
            buf = []
            self._walk_children(tag, 'inline', buf)
            content = ''.join(buf).strip()
            if not content:
                out.append('\\CJKunderline{\\hspace*{2em}}')
            else:
                out.append('\\CJKunderline{' + ''.join(buf) + '}')
            return

        # ---- 删除线 ----
        if name == 's':
            buf = []
            self._walk_children(tag, 'inline', buf)
            content = ''.join(buf).strip()
            if content:
                out.append('\\CJKsout{' + ''.join(buf) + '}')
            return

        # ---- 换行 ----
        if name == 'br':
            if mode == 'cell':
                out.append(' ')
            else:
                # 紧跟图片块等块级内容后的 <br> 会落在行首，生成非法的 \\，
                # 报 “There's no line here to end”，此时直接丢弃
                if not _at_line_start(out):
                    out.append('\\\\')
            return

        # ---- 段落/单元格容器 ----
        if name == 'p':
            if mode == 'cell':
                buf = []
                # 单元格内的 <p> 继续按 cell 模式处理子节点（图片行内引用，
                # 不能生成居中的图片块，否则会拆坏 tabular 行）
                self._walk_children(tag, 'cell', buf)
                if buf and out and out[-1].strip():
                    out.append(' ')
                out.extend(buf)
            else:
                self._walk_children(tag, 'inline', out)
            return

        # ---- 其它容器（span/font/ol/ul/li/div…）直接递归 ----
        self._walk_children(tag, 'inline' if mode != 'cell' else 'cell', out)

    def _subsup_content(self, tag) -> bool:
        """判断 sub/sup 是否有实际内容。

        源站常插入空的上/下标（<sub>&nbsp;</sub>、<sub><sup>&nbsp;</sup></sub>
        等，纯空白、无实际字符），转换会生成空的 $_{ }$ 脚本组，紧跟前一个
        上下标时拼成 Double subscript/superscript 报错（2004_上海#19）。
        纯空白且不含图片的上下标直接丢弃（空白不是内容，不违反“不减少内容”）。
        """
        return bool(tag.get_text().strip()) or tag.find('img') is not None

    def _inline_math(self, node) -> str:
        """把节点内容按数学模式转换成字符串（不包裹 $）。"""
        saved_parts = self._math_parts
        saved_target = self._math_target
        self._math_parts = []
        self._math_target = saved_target
        self._walk_children(node, 'math', None)
        inner = ''.join(self._math_parts)
        self._math_parts = saved_parts
        self._math_target = saved_target
        return inner

    # ---------------- 图片 ----------------

    def _img_opts(self, tag: Tag) -> str:
        """从 style 中解析 width/height（px→pt），过宽则等比缩小。"""
        style = tag.get('style') or ''
        mw = re.search(r'width\s*:\s*([\d.]+)px', style)
        mh = re.search(r'height\s*:\s*([\d.]+)px', style)
        opts = []
        if mw and mh:
            w = float(mw.group(1)) * _PX_TO_PT
            h = float(mh.group(1)) * _PX_TO_PT
            if w > _MAX_IMG_WIDTH_PT:
                scale = _MAX_IMG_WIDTH_PT / w
                w = _MAX_IMG_WIDTH_PT
                h = h * scale
            opts = [f'width={w:.1f}pt', f'height={h:.1f}pt']
        elif mw:
            w = float(mw.group(1)) * _PX_TO_PT
            if w > _MAX_IMG_WIDTH_PT:
                w = _MAX_IMG_WIDTH_PT
            opts = [f'width={w:.1f}pt']
        elif mh:
            opts = [f'height={float(mh.group(1)) * _PX_TO_PT:.1f}pt']
        return ','.join(opts)

    def _image_cmd(self, tag: Tag) -> str:
        src = (tag.get('src') or '').strip()
        if not self.images:
            return f'%% MISSING-IMAGE: {src}'
        name = self.images.register(src)
        if name is None:
            return f'%% MISSING-IMAGE: {src}'
        ref = f'{self.img_prefix}/{name}' if self.img_prefix else name
        opts = self._img_opts(tag)
        opt_str = f'[{opts}]' if opts else ''
        if name.lower().endswith('.svg'):
            base = ref[:-4]
            return f'\\includesvg{opt_str}{{{base}}}'
        return f'\\includegraphics{opt_str}{{{ref}}}'

    def _image_block(self, tag: Tag) -> str:
        if self.img_center:
            return '\\begin{center}\n' + self._image_cmd(tag) + '\n\\end{center}'
        return ('\\begin{figure}[htbp]\n\\centering\n'
                + self._image_cmd(tag) + '\n\\end{figure}')

    def _image_inline(self, tag: Tag) -> str:
        cmd = self._image_cmd(tag)
        if cmd.startswith('%% MISSING-IMAGE'):
            # 单元格内不能放注释（% 会把整行表格注释掉），缺失图片直接留空
            return ''
        return cmd

    # ---------------- 表格 ----------------

    def _cell_text(self, td: Tag) -> str:
        buf: List[str] = []
        self._walk_children(td, 'cell', buf)
        return ''.join(buf).strip()

    def _table_block(self, table: Tag) -> str:
        grid = []  # 每行是 list[dict]，dict: cs/rs/content
        for tr in table.find_all('tr'):
            row = []
            for td in tr.find_all(['td', 'th'], recursive=False):
                if isinstance(td, Tag) and (td.name or '').lower() in ('td', 'th'):
                    row.append({
                        'cs': max(1, int(td.get('colspan') or 1)),
                        'rs': max(1, int(td.get('rowspan') or 1)),
                        'content': self._cell_text(td),
                    })
            if row:
                grid.append(row)
        if not grid:
            return ''
        ncols = max(sum(c['cs'] for c in row) for row in grid)
        nrows = len(grid)
        mat = [[None] * ncols for _ in range(nrows)]
        for r, row in enumerate(grid):
            c = 0
            for cell in row:
                while c < ncols and mat[r][c] is not None:
                    c += 1
                if c >= ncols:
                    break
                mat[r][c] = cell
                for k in range(1, cell['cs']):
                    if c + k < ncols:
                        mat[r][c + k] = 'CS'
                for r2 in range(1, cell['rs']):
                    if r + r2 < nrows:
                        for k in range(cell['cs']):
                            if c + k < ncols:
                                mat[r + r2][c + k] = 'RS'
                c += cell['cs']
        lines = []
        for r in range(nrows):
            parts = []
            c = 0
            while c < ncols:
                cell = mat[r][c]
                if cell is None:
                    parts.append('')
                    c += 1
                elif cell == 'RS' or cell == 'CS':
                    parts.append('')
                    c += 1
                else:
                    content = cell['content']
                    if cell['cs'] > 1:
                        content = f"\\multicolumn{{{cell['cs']}}}{{|c|}}{{{content}}}"
                    if cell['rs'] > 1:
                        content = f"\\multirow{{{cell['rs']}}}{{*}}{{{content}}}"
                    parts.append(content)
                    c += cell['cs']
            lines.append(' & '.join(parts) + ' \\\\ \\hline')
        spec = '|' + 'c|' * ncols
        return ('\\begin{center}\n\\begin{tabular}{' + spec + '}\n\\hline\n'
                + '\n'.join(lines) + '\n\\end{tabular}\n\\end{center}')


# --------------------------------------------------------------------------
# 数学片段合并：把本应连在一起、却被转换过程截断分开的相邻数学片段
# 合并成一个 $...$ 片段。例：
#   $Rc$$\left( {\frac{1}{2} - \frac{1}{4}} \right)$
#       → $Rc\left( {\frac{1}{2} - \frac{1}{4}} \right)$
#   $k$$\dfrac{{{e^2}}}{{{r^2}}}$ = $m$$\dfrac{{{v^2}}}{r}$
#       → $k\dfrac{{{e^2}}}{{{r^2}}} = m\dfrac{{{v^2}}}{r}$
#   $P$ = $UI$                      → $P = UI$
#   $m$$v$$_{0}$ + $mgt$            → $mv_{0} + mgt$
# 规则：
# - 两个 $...$ 片段直接相邻 → 必合并（数学里 $ab$ 与 $a$$b$ 视觉语义一致）；
# - 片段之间只有空白与 ASCII 运算符 = + - < > → 并入数学；
#   两边都是数学片段时，中间的 “ = ” “ + ” 等必是运算符而不是文字；
# - 其它文字（逗号、句号、汉字等）隔开 → 保持分开（各自仍是独立数学片段）。
# --------------------------------------------------------------------------

# 数学片段之间允许并入数学模式的“连接符”字符
_MATH_CONNECTOR_CHARS = set(' \t\n=+-<>')

# 以控制字结尾（如 \Delta）的数学片段，后面紧跟字母/数字时控制字会粘连
# （\Delta + t → \Deltat），拼接时需要补一个空格
_CONTROL_WORD_END_RE = re.compile(r'\\[A-Za-z]+$')

# 单个上/下标组：^{...} 或 _{...}（内容允许一层花括号嵌套，如 ^{{18}}、_{x}）
_SCRIPT_GROUP_RE = re.compile(r'([\^_])\{((?:[^{}]|\{[^{}]*\})*)\}$')


def _glue_guard(left: str, right: str) -> str:
    """拼接两段数学内容，防止控制字与后接字母粘连（\\Delta + t → \\Delta t）。"""
    if right and left and right[0].isalnum() and _CONTROL_WORD_END_RE.search(left):
        return left + ' ' + right
    return left + right


def _safe_script_content(s: str) -> str:
    """让上/下标组内容末尾的反斜杠保持成对，避免转义掉闭合花括号。

    源站偶有残缺公式，如第29届决赛#5 的 <sub>m\\</sub>：内容以单个反斜杠
    结尾，直接写成 _{m\\} 会让 \\} 变成转义花括号、分组无法闭合（Missing }）。
    末尾反斜杠为奇数个时丢弃一个（成对的 \\\\ 是换行，保留）。
    """
    if s.endswith('\\') and _bslashes_before(s, len(s)) % 2 == 1:
        return s[:-1]
    return s


def _join_adjacent(left: str, right: str) -> str:
    """拼接两个直接相邻的数学片段内容。

    相邻的同类上/下标组要合并成一个组，否则 LaTeX 会报 Double
    superscript/subscript：
      ^{a} + ^{b} → ^{ab}；_{a} + _{b} → _{ab}；
      R_{x} + _{ } → R_{x }（并入已有的同类型组）；
    上+下（^{a} + _{b}）直接并排即可。
    """
    ml = _SCRIPT_GROUP_RE.match(left)
    mr = _SCRIPT_GROUP_RE.match(right)
    if mr:  # 右侧是单个上/下标组
        if ml and ml.group(1) == mr.group(1):
            return ml.group(1) + '{' + _glue_guard(ml.group(2), mr.group(2)) + '}'
        # 左侧末尾已有同类型脚本组时并入该组
        me = _SCRIPT_GROUP_RE.search(left)
        if me and me.group(1) == mr.group(1) and me.start() > 0:
            return (left[:me.start()] + me.group(1)
                    + '{' + _glue_guard(me.group(2), mr.group(2)) + '}')
        # 左段含 '（prime，隐式上标）再加 ^ 会 Double superscript（v'_n + ^2），
        # 需把左段成组：{v'_n}^{2}
        if mr.group(1) == '^' and "'" in left:
            return '{' + left + '}' + right
        return left + right if ml else _glue_guard(left, right)
    if ml:
        return left + right
    return _glue_guard(left, right)


def _double_script_risk(left: str, right: str) -> bool:
    r"""判断直接拼接左右两段是否会产生 Double superscript/subscript。

    左段以脚本组（^{…} 或 _{…}）结尾、右段以 ^ 或 _ 开头时，直接拼接会得到
    X^{a}^{b} 这类非法结构（如 10^8 与 ℃ 的 ^{\circ} 被空格隔开却仍合并）。
    """
    return bool(right) and right[0] in '^_' and bool(_SCRIPT_GROUP_RE.search(left))


def _bslashes_before(s: str, j: int) -> int:
    """返回 s[j] 前面连续反斜杠的个数。"""
    k = 0
    while j - 1 - k >= 0 and s[j - 1 - k] == '\\':
        k += 1
    return k


def _find_math_segments(s: str) -> List[Tuple[int, int]]:
    """找到字符串中所有 $...$ 片段（跳过被 \\$ 转义的 $），返回 (起, 止) 位置。"""
    segs: List[Tuple[int, int]] = []
    i, n = 0, len(s)
    while i < n:
        if s[i] != '$' or _bslashes_before(s, i) % 2 == 1:
            i += 1
            continue
        j = i + 1
        while j < n:
            if s[j] == '$' and _bslashes_before(s, j) % 2 == 0:
                break
            j += 1
        if j >= n:  # 没有配对的 $，不处理
            break
        segs.append((i, j + 1))
        i = j + 1
    return segs


def _merge_math_segments(s: str) -> str:
    """把相邻/被连接符隔开的数学片段合并（见本文件上方注释）。"""
    segs = _find_math_segments(s)
    if len(segs) < 2:
        return s
    out: List[str] = []
    pos = 0
    i, n = 0, len(segs)
    while i < n:
        start, end = segs[i]
        content = s[start + 1:end - 1]
        j = i
        while j + 1 < n:
            ns, ne = segs[j + 1]
            gap = s[end:ns]
            if not all(ch in _MATH_CONNECTOR_CHARS for ch in gap):
                break
            if gap:
                nxt = s[ns + 1:ne - 1]
                if _double_script_risk(content, nxt):
                    break
                content += gap + nxt
            else:
                content = _join_adjacent(content, s[ns + 1:ne - 1])
            j += 1
            end = ne
        out.append(s[pos:start])
        out.append('$' + content + '$')
        pos = end
        i = j + 1
    out.append(s[pos:])
    return ''.join(out)
