# 贡献指南（CONTRIBUTING）

感谢参与高考物理真题 LaTeX 档案库！本文件面向**人类协作者**；AI / 自动化见
[`AGENTS.md`](AGENTS.md)，制卷细则见 [`高考物理真题制作规范.md`](高考物理真题制作规范.md)。

## 一、你可以做什么

刷题、校对、排版、制图、编程均可，例如：

- 新增/补全某年某地区试卷（见 [`docs/新增年份SOP.md`](docs/新增年份SOP.md)）；
- 校对已有卷的题干、数据、单位、公式、选项与答案、详解；
- 制作/核对 TikZ 重绘配图（需人工手绘并登记，见下）；
- 修补脚本、文档、检查项。

## 二、环境

本地 TeX Live 2025（`xelatex` + `latexmk`）、Inkscape、poppler、Python、CJK 字体等，
详见 [`docs/运行环境.md`](docs/运行环境.md) 与 [`docs/编译方法.md`](docs/编译方法.md)。

## 三、本地数据（重要）

`JSON/`、`Docx/`、`材料处理/` 是**原始数据 / OCR 产物，已在 `.gitignore` 忽略、只留本地**。
若你没有这些数据：可以只依 JSON 初稿 + 规范制作，但 `check_meta.py`（元数据↔JSON）、
`check_material.py` 等会**跳过并提示**，属正常；完整比对由维护者在有数据的机器上复跑。

## 四、制作一份卷（摘要）

```bash
python3 tools/json_to_tex.py JSON/<年>/<年_地区>.json     # 1 初稿 + 图片
# 2 对照 材料处理/<年>/<地区>/merged.md、（如有）docx、原 PDF 逐题校对重写
make -C 试卷/<年>/<地区> student && make -C 试卷/<年>/<地区> teacher   # 3 两版编译
make -C 试卷/<年>/<地区> check                            # 4 自查（须 0 错误）
```

> 一切命令在**仓库根**执行，用 `make -C 试卷/…`；**不要 `cd`、不要用 `..`**；
> 临时/渲染文件只写 `/tmp/opencode/`。

## 五、提交前自查（必须）

- [ ] `make -C 试卷/<年>/<地区> student` 与 `teacher` 均无错误；
- [ ] `make -C 试卷/<年>/<地区> check` **0 错误**；
- [ ] 若改了文档/进度/异常：`make check-docs` 通过；
- [ ] 若改了 `tools/`：`make tools-test` 通过。

## 六、不要提交的东西

- **原始数据 / OCR 产物**：`JSON/`、`Docx/`、`材料处理/`（已忽略，勿强加）；
- **编译产物**：`*_学生版.pdf`、`*_教师版.pdf`、`TikZ/*.pdf`、`*.log`/`*.aux`/`*.fls`/`*.fdb_latexmk`、`svg-inkscape/`；
- **例外**：`试卷/**/figs/*.pdf` 与 `figs/*.svg` 是个别题的**源图，必须入库**；`TikZ/originals/` 下的原图也应入库。

> 提交前 `git status` 看一眼，确保没有把上述内容 `git add -f` 进去。

## 七、TikZ 重绘（需人工手绘并登记）

规范默认**禁止在转换中引入 TikZ 重绘**；确需重绘者由人工手绘。**标准做法（推荐）**：

1. **命名**：`TikZ/<名>.tex` 与原图 **`figs/<名>` 同名**；
2. **登记**：在 `TikZ/tikz_sources.json` 登记原图。项目已把图放在本卷 `figs/`，
   `original` 直接写 `试卷/<年>/<地区>/figs/<名>.png` 即可，**一般无需再建 `TikZ/originals/`**
   （仅当原图不在 `figs/` 时，才另存 `TikZ/originals/<名>.png` 并入库；确无原图写 `null`）；
3. **接入**：把本卷 `.tex` 中该图的 `figs/<名>` 引用改成 `\onepicture{TikZ/<名>.pdf}`；
4. **核对**：`make -C 试卷/<年>/<地区> tikz-compare` 生成 `tikz_compare/*_重绘前后.png`，
   **逐张核对**（形状/方向/标注/比例），并 `make check-tikz` 通过。

> ⚠️ **不推荐**只上传 `TikZ/*.tex`（未登记、未接入）：`make check-tikz` 会告警，`tikz-compare`
> 虽仍能出图，但**`TikZ` 文件名必须与 `figs` 同名**，否则无法自动配原图。请一次提交完整。

其他硬性规则（元数据 13 项、答案三处一致、每题基本 `\memoanswer{}`、单位用 PhyUnit、
图片只用 ChoiceQuestion 命令、`\frac` 非 `\dfrac` 等）见
[`高考物理真题制作规范.md`](高考物理真题制作规范.md) 第九节自查清单。

## 八、提 PR（Gitee / GitHub）

1. Fork 仓库，新建分支（建议 `feat/<年><地区>`、`fix/<年><地区>`）；
2. 提交信息简洁说明“年份/地区 + 做了什么”（如 `2026 广东：接入 TikZ 配图并登记原图`）；
3. 推送到你的 fork，在 **Gitee**（或 **GitHub 镜像**）发起 Pull Request——
   两边的 PR 模板是同一份自查清单，按提示勾选；
4. 维护者会用 `make fetch-pr` 拉到本地审查（流程见 [`docs/代码审查指南.md`](docs/代码审查指南.md)）。

## 九、只改自己负责的部分

- 尽量只改 `试卷/<年>/<地区>/`（及对应 `进度记录.md`、`异常记录/<年>.md` 行）；
- **避免**改动共享文件（`tools/`、`gaokaozhenti.cls`、`PhyUnit.sty`、`ChoiceQuestion.sty`、文档）
  以免冲突；确需改动请先在 Issue / PR 中说明。
- `试卷/<年>/README.md` 由 `make index` 自动生成，**不要手工编辑**。
