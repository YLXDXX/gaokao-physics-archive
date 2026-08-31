%格式声明
\NeedsTeXFormat{LaTeX2e}[2021-11-15]

\RequirePackage{expl3}

\ProvidesExplPackage{gaokaozhenti} % Package name
{2026-08-31} % Release date
{0.1} % Release version
{高考物理真题·LaTeX档案库 } % Description

\LoadClass[UTF8, a4paper, openany, fontset=windows, zihao=-4,]{ctexbook}
\RequirePackage[top=2.5cm,bottom=2.5cm,left=2cm,right=2cm]{geometry} %页边距

\RequirePackage{amssymb} %公式
\RequirePackage{bm} %公式
\RequirePackage{graphicx} %图片
\RequirePackage{svg}
\RequirePackage[font=bf,labelfont=bf,labelsep=quad]{caption} %标题样式
\RequirePackage{subcaption}
\RequirePackage{enumitem} %列表样式
\RequirePackage{tabularray} %现代表格环境
\UseTblrLibrary{booktabs} %三线表用
\UseTblrLibrary{diagbox} %表头用
\RequirePackage{textgreek} % 配全 mhchem 用，化学式中输入希腊字母
\RequirePackage[version=4]{mhchem} %核素、同位素、化学式
\RequirePackage{xcolor} %更多的颜色名
\RequirePackage{gensymb} %提供了一些单位符号的输入：\degree(°) \celsius(℃) \perthousand(‰) \ohm(Ω) \micro(µ)
\RequirePackage[bookmarksnumbered,draft=false,CJKbookmarks=true,colorlinks=true,linkcolor=blue,hyperindex]{hyperref} %超链接
\RequirePackage{xeCJKfntef} %中文的波浪线、加点、删除线等
%\RequirePackage{circledtext} %带圈文字排版
\RequirePackage{circledsteps} %带圈文字排版
\RequirePackage{derivative} %微分、偏微分符号

%图片标题格式
\captionsetup{subrefformat=parens}
\captionsetup[subfigure]{justification=centering,labelformat=parens}

%列表格式
\setlist[enumerate,1]{label = {\color{blue!60!green}\arabic*.}}
\setlist[enumerate,2]{label = {\color{blue!40!green}(\arabic*)}, ref = (\arabic*)}

%解决中文带圈数字的显示问题
\xeCJKsetcharclass{`①}{`⑩}{1}
%解决罗码数字的显示问题
\xeCJKsetcharclass{`Ⅰ}{`Ⅹ}{1}


%标题设置
\ctexset {
    part/pagestyle = empty,
    chapter = {
    numbering = false,
    beforeskip = -50pt,
    afterskip = 30pt,
    },
    section = {
    name = {,、},
    aftername = {},
    number = \chinese{section},
    format += \raggedright,
    }
}


%题目信息
\NewDocumentCommand \ExamQuestionInfo { m }
{
    %paperName=2025年湖北高考第1题4分,
    %typeId=1, type=单选题,
    %chapter=原子和原子核, point=半衰期,
    %method=无, degree=750, answer=C,
    %其中degree表示难度，从 1000 到 1，750 表示占总人数的 750/1000 都能完成，数值越小，难度越大
}

%罗马数字大小写
 % 小写，如 \ronum{2026}
\NewDocumentCommand \ronum {m}
{
    \int_to_roman:n { #1 }
}
% 大写，如 \Ronum{2026}
\NewDocumentCommand \Ronum {m}
{
    \int_to_Roman:n { #1 }
}
