<!-- 提 PR 前请先读 CONTRIBUTING.md；维护者审查见 docs/代码审查指南.md -->

## 改动说明

- 涉及年份/地区：<!-- 如 2026 广东 -->
- 类型：<!-- 制卷 / 校对 / 排版 / 配图(TikZ) / 工具 / 文档 -->
- 做了什么：

## 自查清单

- [ ] 命令均在**仓库根**用 `make -C 试卷/…` 执行，未 `cd`、未用 `..`
- [ ] `make -C 试卷/<年>/<地区> student` 与 `teacher` 均编译通过
- [ ] `make -C 试卷/<年>/<地区> check` **0 错误**
- [ ] 改了文档/进度/异常：`make check-docs` 通过
- [ ] 改了 `tools/`：`make tools-test` 通过
- [ ] 未提交 `JSON/`、`Docx/`、`材料处理/`、编译产物与日志
- [ ] `figs/*.pdf`、`figs/*.svg`、`TikZ/originals/` 等**源图**已入库
- [ ] `进度记录.md`、`异常记录/<年>.md` 已更新（如涉及）
- [ ] 未手工编辑 `试卷/<年>/README.md`

## TikZ 重绘（如有）

- [ ] `TikZ/<名>.tex` 已在正文用 `\onepicture{TikZ/<名>.pdf}` 引用
- [ ] 已在 `TikZ/tikz_sources.json` 登记原图（无原图者写 `original: null`）
- [ ] 已 `make -C 试卷/<年>/<地区> tikz-compare` 并**逐张人工核对**（形状/方向/标注/比例）

## 关联 Issue

<!-- 如 Fixes #123 -->
