# AGENTS.md · 工具使用与权限约定

> 本文件由本地 `opencode.json` 的 `instructions` 自动加载，**所有（子）会话必须遵守**。
> 目的：避免无关的目录访问授权请求，保证对仓库外零副作用、命令可复现。
> 内容规范仍以根目录 [`AGENTS.md`](../AGENTS.md) 与各制作规范为准；本文件只管**怎么用工具**。

## 1. 工作目录：固定在仓库根，禁止 `cd` / `..`

- 所有 Bash 调用一律 `workdir=<仓库根>`（本仓库顶层目录）。
- **禁止 `cd`**、**禁止用 `..` 做路径穿越**（`../` 会被判为越出工作区，触发外部目录拒绝）。
- 需要到某卷目录执行时，从根目录用：
  - `make -C 试卷/<年>/<地区> student`（不要 `cd 试卷/… && make student`）
  - `python3 tools/xxx.py 试卷/<年>/<地区>/<地区>.tex`
  - `python3 tools/tex_links.py 试卷/<年>/<地区>`

## 2. 临时文件：只放 `/tmp/opencode/`

- 一切中间/临时产物**只写 `/tmp/opencode/`**（已预授权的仓库外目录）。
- **PDF 渲染页统一在此**，例如：
  `pdftoppm -r 150 -png Docx/2008/2008_上海.pdf /tmp/opencode/上海`
- 禁止写裸 `/tmp`、`~`、仓库的父目录或兄弟项目目录。
- 需要长期保留的中间产物放仓库内、且已被 `.gitignore` 的目录。

## 3. 文件操作：优先用专用工具

- 读、找、改优先用 **Read / Glob / Grep / Edit / Write**；
- 不要用 Bash 的 `cat/head/tail/find/grep/sed/awk` 代替上述专用工具（无收益且易误触目录授权）；
- 复制/删除仓库内文件（如复制模板 `Makefile`、把 JSON 图复制到 `figs/`、删除多余图片）
  可用 `cp/mv/rm`，但路径一律相对仓库根，**不得越界到仓库外**。

## 4. 子代理（Task）约定

派发子任务时，**必须在 prompt 里写明**并确保子代理执行：

- `workdir` 固定为仓库根，禁止 `cd` 与 `..`；
- 临时/渲染文件只写 `/tmp/opencode/`；
- 只改自己负责的目录；不改共享文件（`tools/`、`*.sty`、`*.cls`、文档、`opencode.json`）；
- 收尾仍要跑对应卷的 `make -C 试卷/<年>/<地区> check`。

子代理默认加载根 `AGENTS.md`；当存在本地 `opencode.json` 时，本文件也会被一并加载。

## 5. 越界访问

- 本会话的文件工具**不访问仓库以外的文件**（系统配置、其它项目、`~/.texlive` 等）。
- 项目级 `opencode.json` 把 `external_directory` 设为「默认拒绝、仅允许 `/tmp/opencode/**`」：
  仓库外路径除 `/tmp/opencode/` 外会被**直接拒绝**（不再弹窗）。确需访问其它外部路径时，
  先向用户说明理由，由用户临时调整该本地配置。
- 注意：`opencode.json` 为**本地配置、已在 `.gitignore` 忽略、不入库**，本文件只在存在该
  本地配置时才被 `instructions` 自动加载；新克隆环境中**以根目录 `AGENTS.md` 的「工具使用
  与权限」摘要为准**（亦可自行复制一份 `opencode.json`）。
- 修改 `opencode.json` 后需**退出并重启 opencode** 才会生效（配置不热重载）。
