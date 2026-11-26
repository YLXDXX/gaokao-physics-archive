# 交叉校对

借助三份独立来源的成品 PDF（**天利 2025–2026**、**朱玉亮 1978–2024**、
**刘芳 1978–2026**）交叉校对 `试卷/<年>/<地区>/` 下的题目、答案、解析、公式、配图等。
裁定优先级：天利 ＞ 朱玉亮 ＞ 刘芳 ＞ 本仓库材料。

- 完整规范：[`规范.md`](规范.md)
- 总表：[`交叉校对表.md`](交叉校对表.md)（自动生成，**勿手改**）
- 源文件映射：[`mapping.json`](mapping.json)（自动生成）
- 人工别名/例外：[`overrides.json`](overrides.json)
- 校对状态：[`status.json`](status.json)（人工维护）
- 重命名记录：[`rename_manifest.json`](rename_manifest.json)（可回滚）
- 高质量矢量配图：[`HighQualityPic表.md`](HighQualityPic表.md)（自动生成）、
  [`hq_mapping.json`](hq_mapping.json)、[`hq_figmap/`](hq_figmap/)、
  [`hq_apply_log.json`](hq_apply_log.json)

素材 `ProofreadPDF/`（含 `HighQualityPic/`）与 OCR 产物 `交叉校对/材料/`、
匹配对照图 `交叉校对/hq_compare/` 均为**本地、Git 忽略**，不入库。

## 快速上手

```bash
# 首次/源有更新：扫描 → 映射 → 刷新总表（同时补齐 status 默认条目）
make proofread-plan

# 仅首次：把源 PDF 按本仓库命名方式就地重命名（默认只预览）
make proofread-rename
make proofread-rename-apply
# 如需回滚：make proofread-rename-revert

# 查看某卷对应哪份源、当前状态
make proofread-show UNIT=2024/辽宁

# 校验映射/源文件/状态/总表一致
make proofread-check

# OCR（先看计划；真正识别极耗时，最后再启动）
make proofread-ocr-plan
make proofread-ocr-batch

# 高质量矢量配图（HighQualityPic）
make hq-plan                         # 扫描 → hq_mapping.json + HighQualityPic表.md
make hq-rename && make hq-rename-apply   # 文件夹/文件规范化（可 revert）
make hq-match UNIT=1978/全国          # 生成逐图匹配草表 + 对照图
# 看对照图，改 hq_figmap/<年>_<地区>.json：status="apply"；必要时填 crop
make hq-apply UNIT=1978/全国 ARGS=--write   # 成功后自动标 applied
make hq-check
```

## 更新校对进度

编辑 `status.json` 中对应 `"<年>/<地区>"` 条目：

```json
"2024/辽宁": {
  "status": "已完成",
  "date": "2026-11-24",
  "note": "以天利/朱源为底本逐题核对；改正题干 2 处、答案 1 处，配图替换 1 张"
}
```

状态取值：`未开始` / `素材就绪` / `校对中` / `已完成` / `待人工核验` / `无源`。
然后运行：

```bash
make proofread-table
make proofread-check
```

异常/冲突记入 `异常记录/<年>.md`（类别取现有枚举，问题中注明“交叉校对”）。

## 当前概况

> 截至 2026-11-26，以 [`交叉校对表.md`](交叉校对表.md) 为准。

- 本仓库 413 套卷；其中有他源可校 **363** 套、三源均无 **50** 套。
- 他源有、本仓库无对应卷 **6** 套（朱/刘合计 10 条来源记录；见总表第三节）。
- **他源 OCR**（2026-11-26）：天利 96、朱源 634、刘源 368 均已完成，`merged.md` 齐备，
  `ocrpipe check` 三树通过；可校的 363 套状态已由 `未开始` 置为 `素材就绪`，
  `无源` 卷列在总表第二节。
- **天利 38 套已接入**（2025–2026，47 套 / 94 份有效卷）：卷名规范化后映射入
  `mapping.json`；另有 1 套 2 份扫描件（2025 `西北四省`）与 `陕晋青宁` 同套，
  已在 `overrides.json` 的 `ignore` 中排除，保留文字版。
- 已知命名差异（如 1991 三南→湖南云南海南、2001 广东河南→粤豫、2024 黑吉辽→辽宁、
  2025 山陕青宁/陕晋青宁→陕晋宁青、辽吉黑蒙→黑吉辽内、2026 黑吉辽蒙/辽吉黑蒙→黑吉辽）
  已在 `overrides.json` 登记并注明依据。
- HighQualityPic：313/413 套有 HQ 图（试题图 5817、答案图 1153）；8 个 HQ 文件夹（4 套卷）
  在本仓库无对应卷。已完成试点：**1978/全国**（5 张）、**1979/全国**（11 张，含
  四图选项与答案图裁边），详见 `hq_apply_log.json` 与 `异常记录/1978.md`、`1979.md`。
- 其余卷按 `交叉校对/规范.md` 第十节逐卷处理：先 `hq-match`，人工看对照图后再
  `hq-apply`；不能替换的原因记入对应年份异常记录。
