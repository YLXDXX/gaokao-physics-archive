#!/usr/bin/env python3
"""tools/json_to_tex.py —— 由平台 JSON 生成某卷 LaTeX 初稿 + 图片素材

用途：高考真题库建设的**第一步**——把 ``JSON/<年>/<...>.json`` 处理为“基本材料”：
题目元信息、题干、选项、答案、图片。图片按“题号（+子图字母）”短名复制到试卷目录的
``figs/``，并据此生成一份 ``<地区>.tex`` 初稿。

> 注意：这是**初稿**。JSON 的题干/答案/解析是纯文本（含 ``\\(...\\)`` 数学），
> 公式排版、图片的多子图拆分与摆放、解析补全等仍须对照 OCR 后的 markdown 与
> 原 PDF 逐题校对（见 `材料处理与OCR规范.md`、`高考物理真题制作规范.md`）。

用法::

    # 依 JSON 路径自动推断年份/地区，输出到 试卷/<年>/<地区>/
    python3 tools/json_to_tex.py JSON/2026/2026_湖北.json

    # 显式指定输出目录；--force 覆盖已存在的 .tex
    python3 tools/json_to_tex.py JSON/2026/2026_云南.json --out 试卷/2026/云南 --force

    # 理综节选：加卷级标记（保留平台原题号，显示序号由 enumerate 自动生成）
    # 注意：--renumber 会改写 %% number，使 check_meta.py（要求与 JSON 原题号一致）
    #       失败，制卷时通常不用。
    python3 tools/json_to_tex.py JSON/2000/2000_天津.json --paper-type 理综物理部分

    # 只导出基础材料（图 + markdown），不生成 tex
    python3 tools/json_to_tex.py JSON/2026/2026_湖北.json --material-only

初稿已尽量贴近规范：缺 `memo` 自动写占位 `\\memoanswer`；非选择题按小问生成
`\\jdanswer`（多小问 → `enumerate`）；同题多图 → `\\twopicture…`；图片选项 →
`\\fourchoices[ispicture=true]`；`（A）`/`A．` 选项均可解析；理综节选加 `--paper-type`
（不用 `--renumber`，以免与 `check_meta.py` 冲突）。
但仍须对照 `merged.md` 与原 PDF 逐题校对重写。
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FIELDS_ORDER = [
    "number", "paperName", "typeId", "type", "chapter", "point", "method",
    "score", "degree", "duplicateId", "body", "answer", "memo",
]

GREEK = {
    "alpha": "\\alpha", "beta": "\\beta", "gamma": "\\gamma", "delta": "\\delta",
    "epsilon": "\\epsilon", "theta": "\\theta", "lambda": "\\lambda", "mu": "\\mu",
    "nu": "\\nu", "pi": "\\pi", "rho": "\\rho", "sigma": "\\sigma", "tau": "\\tau",
    "phi": "\\varphi", "omega": "\\omega", "Delta": "\\Delta", "Omega": "\\Omega",
}

ENTITY_MAP = {
    "&times;": "$\\times$", "&minus;": "-", "&ge;": "$\\ge$", "&le;": "$\\le$",
    "&ne;": "$\\ne$", "&deg;": "$^\\circ$", "&infin;": "$\\infty$",
    "&sum;": "$\\sum$", "&radic;": "$\\sqrt{}$", "&asymp;": "$\\approx$",
    "&rarr;": "$\\to$", "&harr;": "$\\leftrightarrow$",
}

# 常见复合单位的保守预映射（→ PhyUnit 宏），减少初稿中的裸单位。
# 仅匹配“不可能被当作变量运算”的复合单位，单字母单位（m/s/kg…）不在此处理。
UNIT_PRE_MAP = [
    # m/s² 的多种形态：m/$s^{2}$、m/s$^{2}$、m/s^2、m/s²、m/s2
    (re.compile(r"m\s*/\s*\$?s\s*\^\s*\{?2\}?\$|m\s*/\s*s(?:\^2|²|2)"), r"\\Umsq"),
    (re.compile(r"(?<![A-Za-z])km\s*/\s*h(?![A-Za-z])"), r"\\Ukmh"),
    (re.compile(r"(?<![A-Za-z\\])m\s*/\s*s(?![A-Za-z0-9$])"), r"\\Ums"),
    (re.compile(r"Ω\s*·\s*m|\\Omega\s*\\cdot\s*m"), r"\\UOm"),
]


def units_to_phyunit(s: str) -> str:
    """把常见复合单位（m/s、m/s²、km/h、Ω·m）预映射为 PhyUnit 宏。"""
    for pat, rep in UNIT_PRE_MAP:
        s = pat.sub(rep, s)
    return s


def unescape_entities(s: str) -> str:
    for k, v in ENTITY_MAP.items():
        s = s.replace(k, v)
    for name, tex in GREEK.items():
        s = s.replace(f"&{name};", f"${tex}$")
    s = s.replace("&nbsp;", " ").replace("&ensp;", " ").replace("&emsp;", " ")
    s = s.replace("&ldquo;", "“").replace("&rdquo;", "”")
    s = s.replace("&lsquo;", "‘").replace("&rsquo;", "’")
    s = _html.unescape(s)
    return s


# 早期（如 2000 年）试卷常用的全角数学/标点符号 → 半角
FULLWIDTH_MAP = {
    "＞": ">", "＜": "<", "＝": "=", "＋": "+", "－": "-", "ー": "-",
    "−": "-", "–": "-", "×": "$\\times$", "÷": "$\\div$",
    "∶": ":", "∽": "$\\sim$", "≈": "$\\approx$", "≠": "$\\ne$",
    "≤": "$\\le$", "≥": "$\\ge$", "∞": "$\\infty$", "°": "$^\\circ$",
    "Ω": "$\\Omega$", "μ": "$\\mu$", "ρ": "$\\rho$", "π": "$\\pi$",
    "θ": "$\\theta$", "α": "$\\alpha$", "β": "$\\beta$", "γ": "$\\gamma$",
    "λ": "$\\lambda$", "Δ": "$\\Delta$", "φ": "$\\varphi$",
    "√": "$\\sqrt{}$", "⊥": "$\\perp$", "∥": "$\\parallel$",
}


def html_to_tex(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # 平台用 \(...\) 表示行内公式
    s = re.sub(r"\\\((.*?)\\\)", r"$\1$", s, flags=re.S)
    s = unescape_entities(s)
    for k, v in FULLWIDTH_MAP.items():
        s = s.replace(k, v)
    # 去掉直接包裹上/下标的 <em>（平台常把上标整体包在 em 里）
    s = re.sub(r"<em>\s*((?:<su[bp]>.*?</su[bp]>)+)\s*</em>", r"\1", s, flags=re.S)
    # 变量 + 上下标：<em>R</em><sub>0</sub> -> $R_{0}$
    s = re.sub(r"<em>\s*(.*?)\s*</em>\s*<sub>\s*(.*?)\s*</sub>", r"$\1_{\2}$", s, flags=re.S)
    s = re.sub(r"<em>\s*(.*?)\s*</em>\s*<sup>\s*(.*?)\s*</sup>", r"$\1^{\2}$", s, flags=re.S)
    # 核素等前/后置上下标：<sup>90</sup><sub>39</sub> -> $^{90}_{39}$
    s = re.sub(r"<sup>\s*(.*?)\s*</sup>\s*<sub>\s*(.*?)\s*</sub>", r"$^{\1}_{\2}$", s, flags=re.S)
    s = re.sub(r"<sub>\s*(.*?)\s*</sub>\s*<sup>\s*(.*?)\s*</sup>", r"$_{\1}^{\2}$", s, flags=re.S)
    # 普通上下标（带底数）
    s = re.sub(r"([A-Za-z0-9])\s*<sub>\s*(.*?)\s*</sub>", r"$\1_{\2}$", s, flags=re.S)
    s = re.sub(r"([A-Za-z0-9])\s*<sup>\s*(.*?)\s*</sup>", r"$\1^{\2}$", s, flags=re.S)
    # 变量
    s = re.sub(r"<em>\s*(.*?)\s*</em>", r"$\1$", s, flags=re.S)
    # 孤立上下标
    s = re.sub(r"<sub>\s*(.*?)\s*</sub>", r"$_{\1}$", s, flags=re.S)
    s = re.sub(r"<sup>\s*(.*?)\s*</sup>", r"$^{\1}$", s, flags=re.S)
    s = re.sub(r"<strong>\s*(.*?)\s*</strong>", r"\\textbf{\1}", s, flags=re.S)
    s = re.sub(r"<u>\s*(.*?)\s*</u>", r"\\underline{\1}", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</?(?:span|div|p|tbody|tr|td|table)[^>]*>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("$$", "$")  # 合并相邻行内公式产生的空 $
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = units_to_phyunit(s)
    return s.strip()


def split_paragraphs(body: str) -> list[str]:
    """按 </p> / <br> 切分；返回去标签后的段落文本（图片另由 extract_images 处理）。"""
    raw = re.split(r"</p>|<br\s*/?>", body)
    out = []
    for r in raw:
        if not r.strip():
            continue
        out.append(r)
    return out


def split_options(text: str) -> list[tuple[str, str]]:
    """把含 ``（A）…（B）…`` 或 ``A．…B．…`` 的段落切分为 [(字母, 内容), …]。"""
    # 在选项标志前切分：全角括号 （A） 或 字母 + 顿号/句点 A．A、A.
    parts = re.split(
        r"(?=(?:(?<![A-Za-z0-9])[A-I][．.、][ \t]|（[A-I]）))", text
    )
    opts = []
    for p in parts:
        m = re.match(r"^(?:（([A-I])）|([A-I])[．.、])[ \t]*(.*)$",
                     p.strip(), flags=re.S)
        if m:
            letter = m.group(1) or m.group(2)
            opts.append((letter, m.group(3).strip()))
    return opts


def convert_answer(answer_html: str, is_choice: bool) -> str:
    txt = html_to_tex(answer_html or "")
    if is_choice:
        return re.sub(r"[^A-I]", "", txt)
    # 非选择题：按小问返回，保留（1）（2）结构
    return txt


def convert_memo(memo_html: str) -> str:
    return html_to_tex(memo_html or "")


def image_ext(src: str) -> str:
    return Path(src).suffix.lower() or ".png"


CHOICE_CMD = {2: "two", 3: "three", 4: "four", 5: "five",
              6: "six", 7: "seven", 8: "eight", 9: "nine"}
MEMO_PLACEHOLDER = "本题原卷及材料中未提供详解，待补充。"


def _fig_inner(name: str) -> str:
    """图片文件名 → ChoiceQuestion 命令内容（SVG 用 \\includesvg 去扩展名）。"""
    rel = f"figs/{name}"
    return f"\\includesvg{{{rel[:-4]}}}" if Path(name).suffix.lower() == ".svg" else rel


def _answer_paragraphs(answer_html: str) -> list[str]:
    """把答案 HTML 按段落转为若干条答案文本。"""
    return [t for t in (html_to_tex(p) for p in split_paragraphs(answer_html or "")) if t]


def _emit_images(names: list[str], *, align: str | None = None,
                 label_base: str | None = None) -> list[str]:
    """生成图片命令：1 张 → \\onepicture；多张 → \\twopicture…\\ninepicture（自动编号）。"""
    if not names:
        return []
    if len(names) == 1:
        opt = f"[align={align}]" if align else ""
        return [f"\\onepicture{opt}{{{_fig_inner(names[0])}}}"]
    cmd = CHOICE_CMD.get(len(names))
    if cmd is None:  # 超过 9 张：逐张单图
        opt = f"[align={align}]" if align else ""
        return [f"\\onepicture{opt}{{{_fig_inner(n)}}}" for n in names]
    opts: list[str] = []
    if label_base is None:
        label_base = "fig"
    for i in range(len(names)):
        opts.append(f"label{chr(65 + i)}={label_base}{chr(97 + i)}")
    if align:
        opts.append(f"align={align}")
    out = [f"\\{cmd}picture[{', '.join(opts)}]"]
    out.extend("{" + _fig_inner(n) + "}" for n in names)
    return out


def process_paper(json_path: Path, out_dir: Path, *, force: bool,
                  material_only: bool, renumber: bool = False,
                  paper_type: str = "", material_root: Path | None = None) -> int:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    m = re.match(r"(\d{4})_(.+)\.json$", json_path.name)
    if not m:
        print(f"[错误] 无法从文件名推断年份/地区：{json_path.name}", file=sys.stderr)
        return 1
    year, region = m.group(1), m.group(2)
    title = f"{year}年{region}"

    figs_dir = out_dir / "figs"
    figs_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{region}.tex"
    if tex_path.exists() and not force and not material_only:
        print(f"[跳过] {tex_path} 已存在（--force 覆盖）")
        return 0

    json_dir = json_path.parent
    items = data.get("items", [])
    lines: list[str] = [
        "\\ifdefined\\gkver\\else\\def\\gkver{student}\\fi",
        "\\documentclass[\\gkver]{gaokaozhenti}",
        "\\begin{document}",
        "",
        f"\\chapter{{{title}}}",
    ]
    if paper_type:
        lines.append(f"%% paperType: {paper_type}")
    if renumber:
        src_nums = ", ".join(str(it.get("number")) for it in items)
        lines.append(f"%% sourceNumbers: {src_nums}")
    lines.extend(["", "\\begin{enumerate}"])
    material: list[str] = [f"# {title} 基础材料（由 JSON 生成，仅供校对）", ""]
    warnings: list[str] = []

    for idx, it in enumerate(items, start=1):
        num = it.get("number")
        meta_num = idx if renumber else num
        num2 = f"{int(meta_num):02d}" if isinstance(meta_num, int) else str(meta_num).zfill(2)
        body = it.get("body") or ""
        answer_html = it.get("answer") or ""
        memo_html = it.get("memo") or ""
        type_name = it.get("type") or ""
        type_id = it.get("typeId")
        is_choice = type_id in (1, 2) or "选择题" in type_name

        # ---- 收集正文图片（按出现顺序，去重）----
        imgs = re.findall(r"<img[^>]*src=\"([^\"]+)\"[^>]*>", body)
        seen: list[str] = []
        for src in imgs:
            if src not in seen:
                seen.append(src)
        img_names: list[str] = []
        for i, src in enumerate(seen):
            ext = image_ext(src)
            name = f"{num2}{ext}" if len(seen) == 1 else f"{num2}{chr(ord('a') + i)}{ext}"
            src_abs = json_dir / src
            dst = figs_dir / name
            if src_abs.exists():
                if not dst.exists() or force:
                    shutil.copy2(src_abs, dst)
            else:
                warnings.append(f"第 {num} 题 JSON 缺图：{src}")
            img_names.append(name)

        # ---- 解析段落 / 选项 ----
        paras = split_paragraphs(body)
        stem_parts: list[str] = []
        subq_texts: list[str] = []
        option_pairs: list[tuple[str, str]] = []
        opt_img = 0
        for p in paras:
            inner = re.sub(r"<img[^>]*>", "", p)
            txt = html_to_tex(inner)
            raw_imgs = re.findall(r"<img[^>]*src=\"([^\"]+)\"[^>]*>", p)
            if raw_imgs and (not txt.strip()
                             or re.fullmatch(r"[（(]?[A-I][）)、．.]?", txt.strip())):
                opt_img += 1  # 图片选项段落（选项字母由宏自动生成）
                continue
            if not txt:
                continue
            opts = split_options(txt)
            if opts and (not option_pairs or opts[0][0] == chr(ord("A") + len(option_pairs))):
                option_pairs.extend(opts)
            elif option_pairs:
                subq_texts.append(txt)  # 选项之后的内容（如实验题小问）
            elif (not is_choice) and re.match(r"^[（(]?\s*\d+\s*[）)、．.]", txt):
                subq_texts.append(txt)  # 非选择题中形如“（1）…”的小问
            else:
                stem_parts.append(txt)
        # 去掉纯选项标记段落（图片选项时题干会残留“（A）（B）…”）
        stem_parts = [t for t in stem_parts
                      if not re.fullmatch(r"[（(]?[A-I][）)、．.]?", t.strip())]

        answer_letters = convert_answer(answer_html, True) if is_choice else ""
        stem = "\n\n".join(stem_parts)
        if is_choice:
            stem = re.sub(r"[（(]\s*[)）]\s*$",
                          lambda _m: "\\xzanswer{%s}" % (answer_letters or "Z"), stem)

        # 图片选项判定：选择题、无文字选项、且至少有 2 个“图片选项段落”
        image_options = is_choice and not option_pairs and opt_img >= 2

        question_lines: list[str] = []
        if is_choice:
            if stem:
                question_lines.append(stem)
            if image_options:
                cmd = CHOICE_CMD.get(len(img_names))
                if cmd:
                    question_lines.append(
                        f"\\{cmd}choices[answer={answer_letters or 'Z'}, ispicture=true, h=2.7cm]")
                    question_lines.extend("{" + _fig_inner(n) + "}" for n in img_names)
                else:
                    warnings.append(f"第 {num} 题图片选项数 {len(img_names)} 异常，请人工核对")
                    question_lines.extend(_emit_images(img_names))
            else:
                question_lines.extend(_emit_images(
                    img_names, label_base=f"{year}{region}{num2}"))
                if option_pairs:
                    cmd = CHOICE_CMD.get(len(option_pairs), "four")
                    question_lines.append(f"\\{cmd}choices[answer={answer_letters or 'Z'}]")
                    question_lines.extend("{" + content + "}" for _, content in option_pairs)
                elif img_names:
                    warnings.append(f"第 {num} 题未解析出选项，请人工补充")
        else:
            if stem:
                question_lines.append(stem)
            if len(subq_texts) >= 2:
                question_lines.append("\\begin{enumerate}")
                for t in subq_texts:
                    t = re.sub(r"^[（(]?[0-9]+[）)、．.]\s*", "", t)
                    question_lines.append("\t\\item")
                    question_lines.append("\t" + t)
                question_lines.append("\\end{enumerate}")
            elif subq_texts:
                question_lines.extend(subq_texts)
            question_lines.extend(_emit_images(
                img_names, align="right", label_base=f"{year}{region}{num2}"))

        # ---- 元数据 + 正文 ----
        lines.append("\\item")
        lines.append(f"%% number: {meta_num}")
        lines.append(f"%% paperName: {it.get('paperName','')}")
        lines.append(f"%% typeId: {type_id}")
        lines.append(f"%% type: {type_name}")
        lines.append(f"%% chapter: {it.get('chapter','')}")
        lines.append(f"%% point: {it.get('point','')}")
        lines.append(f"%% method: {it.get('method','')}")
        lines.append(f"%% score: {it.get('score','')}")
        lines.append(f"%% degree: {it.get('degree','')}")
        lines.append(f"%% duplicateId: {it.get('duplicateId','')}")
        lines.append("%% body:")
        lines.extend(question_lines)
        lines.append("%% answer: " + (answer_letters if is_choice else ""))

        # ---- 非选择题：\jdanswer（多小问 → enumerate） ----
        if not is_choice:
            ans_paras = _answer_paragraphs(answer_html)
            if len(ans_paras) >= 2:
                lines.append("\\jdanswer{")
                lines.append("\\begin{enumerate}")
                for t in ans_paras:
                    t = re.sub(r"^\s*[（(]?[0-9]+[）)、．.]\s*", "", t)
                    lines.append("\t\\item")
                    lines.append("\t" + t)
                    lines.append("")
                lines.append("\\end{enumerate}")
                lines.append("}")
            else:
                lines.append("\\jdanswer{")
                lines.extend(ans_paras)
                lines.append("}")

        # ---- 详解：缺则占位 ----
        lines.append("%% memo:")
        memo = convert_memo(memo_html)
        if not memo:
            memo = MEMO_PLACEHOLDER
            warnings.append(f"第 {num} 题 JSON 无详解，已写占位")
        lines.append("\\memoanswer{")
        lines.extend(memo.splitlines())
        lines.append("}")
        lines.append("")

        material.append(f"## 第 {num} 题（{type_name}）")
        material.append("- 图片：" + (", ".join(img_names) if img_names else "无"))
        material.append(f"- 答案：{convert_answer(answer_html, is_choice)}")
        material.append(f"- 题干：\n\n{stem or '(空)'}")
        if memo and memo != MEMO_PLACEHOLDER:
            material.append(f"- 解析：\n\n{memo}")
        material.append("")

    lines.append("\\end{enumerate}")
    lines.append("")
    lines.append("\\end{document}")
    lines.append("")

    if not material_only:
        tex_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[完成] 初稿 {tex_path}")
    mat_dir = (material_root or ROOT) / "材料处理" / year / region
    mat_dir.mkdir(parents=True, exist_ok=True)
    (mat_dir / "json_material.md").write_text("\n".join(material), encoding="utf-8")
    print(f"[完成] 材料 {mat_dir / 'json_material.md'}；图片 {len(list(figs_dir.glob('*')))} 张")
    if warnings:
        print("[需人工核验]")
        for w in dict.fromkeys(warnings):
            print("  -", w)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="由平台 JSON 生成某卷 LaTeX 初稿与图片素材")
    ap.add_argument("json", type=Path, help="JSON 文件路径（JSON/<年>/<...>.json）")
    ap.add_argument("--out", type=Path, default=None, help="输出试卷目录（缺省按年份/地区推断）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 .tex 与图片")
    ap.add_argument("--material-only", action="store_true", help="只导出图片与材料 markdown")
    ap.add_argument("--renumber", action="store_true",
                    help="题号按顺序重编 1..N（原题号记入卷级 %% sourceNumbers）；慎用："
                         "会改写 %% number，与 check_meta.py（要求与 JSON 一致）冲突")
    ap.add_argument("--paper-type", default="", help="卷级 %% paperType 注释（如“理综物理部分”）")
    args = ap.parse_args(argv)

    json_path = args.json.resolve()
    if not json_path.exists():
        print(f"[错误] 找不到 {json_path}", file=sys.stderr)
        return 1
    if args.out:
        out_dir = args.out.resolve()
    else:
        m = re.match(r"(\d{4})_(.+)\.json$", json_path.name)
        if not m:
            print("[错误] 无法推断输出目录，请用 --out", file=sys.stderr)
            return 1
        out_dir = ROOT / "试卷" / m.group(1) / m.group(2)
    return process_paper(json_path, out_dir, force=args.force,
                         material_only=args.material_only,
                         renumber=args.renumber, paper_type=args.paper_type)


if __name__ == "__main__":
    sys.exit(main())
