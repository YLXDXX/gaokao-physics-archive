# ===========================================================================
#  高考物理真题·LaTeX档案库 —— 根目录 Makefile
#
#  用途：批量编译 试卷/<年份>/<地区>/ 下的各套真题（每份试卷为一份可独立编译的文档）。
#        单份试卷的编译由各卷目录内的 Makefile 负责。
#
#  用法：
#    make / make all   编译全部试卷（TikZ 图片 + 学生版 + 教师版）
#    make student      仅编译各卷学生版（答案留空、不含详解）
#    make teacher      仅编译各卷教师版（含答案与详解）
#    make tikz         仅编译各卷 TikZ/ 下的独立图片（生成 PDF）
#    make tikz-compare 为各卷生成「重绘 TikZ 与原图」对比图（tikz_compare/）
#    make check        规范自查（结构/元数据、内容、答案、公式编号、单位、版面、缺字、跨项复查
#                      + TikZ 登记 + 裁剪 recipe + 材料完整性 + 文档一致性与体检）
#    make check-tikz   重绘 TikZ 原图登记一致性检查
#    make check-recrop 多子图裁剪 recipe 一致性检查
#    make material PDF=<源PDF> OUT=材料处理/<年>/<地区>   跑某卷的 OCR 材料管线
#    make material-merge   为 材料处理/ 下各卷生成/校验 merged.md
#    make extract-images   从源 PDF 无损提取内嵌图到 材料处理/…/pdfimages/
#    make check-material   材料四要素/图片引用/逐页源数据/底稿漂移检查
#    make figsize-audit    图片尺寸处理前审计（只读；ARGS 可传目录/--json/--probe-pdf）
#    make figsize-plan     按 figures.map.json + 候选 manifest 生成 figures.manifest.json
#    make figsize-apply    按 figures.manifest.json 回填 .tex 尺寸（默认预览，--write 落盘）
#    make figsize-check    校验 manifest ↔ .tex 尺寸键 + PNG pHYs / PDF / SVG 纵横比
#                          ARGS="… --strict-assets" 要求 SVG 必须先迁 PDF
#    make figsize-status   列出图片尺寸 done / todo（全面铺开时先跑，done 的跳过）
#    make figsize-review   批量复核清单（None / d>5% / 异常尺寸 / 未引用；ARGS 传目录）
#    make figsize-check-ext UNIT=试卷/…  用 OCRPipeLine 3.1.1 交叉校验（5%/15%，--strict）
#    make figsize-apply-ext UNIT=试卷/… 用 OCRPipeLine 3.1.1 预演安全回填（ARGS=--write 落盘）
#    make figsize-status-ext [ARGS="试卷 --only-todo"] 用 OCRPipeLine 3.1.1 列 done/todo
#    make ocr-plan|ocr-status|ocr-batch  OCR 流水线（外部 OCRPipeLine；ARGS 透传）
#    make tools-test   运行 tools 单元测试（textfix / 元数据 / 内容 / 索引）
#    make links        为全部试卷目录创建指向根公共文件的软链接
#    make fetch-pr PR=1 [REMOTE=gitee]  接取远程 PR 到本地分支 pr/1（审查用）
#    make pr-check PR=1 [REMOTE=gitee]  接取后只对 PR 改动的试卷目录跑 check
#    make clean        清理各卷辅助文件
#    make distclean    清理各卷辅助文件与 PDF 成品
#
#  并行：各卷相互独立，可并行编译。JOBS 指定并发线程数，默认 1（串行）；
#        可用 make JOBS=8 指定，也可用 make -j8（取 -jN 的 N）。
#        每个单元内部仍由各自的 Makefile 控制（此处以 JOBS=1 串行，避免超配）。
#  Inkscape：svg 宏包每张图调用一次 Inkscape；并发调用会因 Gio::DBus::Error 崩溃。
#        各卷 Makefile 已把 tools/bin/inkscape（flock 串行化包装）加入 PATH，故可安全并行。
#        若并行曾失败：latexmk 会把错误记入 *.fdb_latexmk，先 make distclean 再重编。
#  软链接：各卷 make/all/student/teacher 会自动建立指向根公共文件的相对软链接（见 make links），
#        便于用 TeXStudio 直接打开并编译各卷 .tex。
# ===========================================================================
PAPERS := 试卷/*/*
# 指定年份只处理该年（如 make check YEAR=2000），成千套时便于增量自查
ifdef YEAR
PAPERS := 试卷/$(YEAR)/*
endif

ifeq ($(origin JOBS),undefined)
JOBS := 1
_JN := $(patsubst -j%,%,$(filter -j%,$(MAKEFLAGS)))
ifneq ($(_JN),)
JOBS := $(_JN)
endif
endif
# 按 JOBS 并行执行从 stdin 读取的 NUL 分隔目录（-r：无输入时不执行）
XARGS := xargs -0 -r -n1 -P $(JOBS)

# $(call RUN_DIRS,<目录通配符>,<子目标>)
define RUN_DIRS
	@for d in $(1); do [ -f "$$d/Makefile" ] || continue; printf '%s\0' "$$d"; done \
		| $(XARGS) sh -c 'echo "===== $$1 : $(2) ====="; $(MAKE) -s -C "$$1" JOBS=1 $(2)' sh || exit 1
endef

.PHONY: all student teacher tikz tikz-compare check check-tikz check-recrop links \
        clean distclean material material-batch material-merge extract-images check-material figsize-audit figsize-automap figsize-merge-fallback figsize-fix-refs figsize-unit figsize-plan figsize-apply figsize-check figsize-status figsize-review \
        figsize-check-ext figsize-apply-ext figsize-status-ext tools-test \
        ocr-plan ocr-status ocr-batch \
        index progress check-docs check-changed ci fetch-pr pr-check

all:
	$(call RUN_DIRS,$(PAPERS),all)

# 仅学生版 / 仅教师版（教师版显示答案与详解）
student:
	$(call RUN_DIRS,$(PAPERS),student)

teacher:
	$(call RUN_DIRS,$(PAPERS),teacher)

tikz:
	$(call RUN_DIRS,$(PAPERS),tikz)

tikz-compare:
	$(call RUN_DIRS,$(PAPERS),tikz-compare)

check:
	$(call RUN_DIRS,$(PAPERS),check)
	@echo "===== 重绘 TikZ 原图登记一致性检查 ====="
	@$(OCRPIPE) check-tikz 试卷
	@echo "===== 多子图裁剪 recipe 一致性检查 ====="
	@$(OCRPIPE) check-recrop 试卷
	@echo "===== 材料处理产物完整性检查 ====="
	@if [ -d 材料处理 ]; then $(OCRPIPE) check --root 材料处理; \
	  else echo "  （跳过：未找到 材料处理/，为本地忽略目录）"; fi
	@echo "===== 编译日志缺字检查 ====="
	@python3 tools/check_glyphs.py
	@echo "===== 成品跨项复查 ====="
	@python3 tools/check_review.py
	@echo "===== 文档索引一致性检查 ====="
	@python3 tools/check_docs.py
	@echo "===== 文档体检（交叉引用/过时命令）====="
	@python3 tools/check_docs_text.py

# 进度/索引文档（见 docs/编译方法.md）
index:
	@python3 tools/gen_index.py --write

progress:
	@python3 tools/status.py

check-docs:
	@python3 tools/check_docs.py
	@python3 tools/check_docs_text.py

# 仅自查 git 有改动的试卷目录（规模大时使用）
check-changed:
	@DIRS=$$( { git -c core.quotepath=false diff --name-only; \
		git -c core.quotepath=false ls-files --others --exclude-standard; } \
		| awk -F/ '$$1=="试卷" && NF>=3 {print $$1"/"$$2"/"$$3}' | sort -u ); \
	if [ -z "$$DIRS" ]; then echo "无试卷改动，跳过。"; exit 0; fi; \
	for d in $$DIRS; do [ -f "$$d/Makefile" ] || continue; \
		echo "===== $$d : check ====="; \
		$(MAKE) -s -C "$$d" JOBS=1 check || exit 1; done

# ---------------------------------------------------------------------------
# 接取远程 PR / 审查（详见 docs/代码审查指南.md）
#   make fetch-pr PR=1 [REMOTE=gitee]   拉取 PR 到本地分支 pr/1，并打印 diff 概况
#   make pr-check PR=1 [REMOTE=gitee]   接取后对 PR 改动的试卷目录先 make all 再 check
#                                       （先编译 TikZ/两版，才能查出编译期问题，如缺字）
# REMOTE 默认 gitee（本仓库还配置了 github / origin）。
# ---------------------------------------------------------------------------
REMOTE ?= gitee

fetch-pr:
	@[ -n "$(PR)" ] || { echo "用法: make fetch-pr PR=<编号> [REMOTE=gitee]"; exit 1; }
	git fetch $(REMOTE)
	git fetch $(REMOTE) refs/pull/$(PR)/head:pr/$(PR)
	@echo ">> 已取到 PR #$(PR) → 本地分支 pr/$(PR)"
	@git --no-pager diff --stat $(REMOTE)/main...pr/$(PR) 2>/dev/null \
		|| echo "（提示：远端基线 $(REMOTE)/main 不可用，可改用 REMOTE=origin）"
	@echo ">> 切换审查：git switch pr/$(PR)   （返回：git switch -）"

pr-check:
	@[ -n "$(PR)" ] || { echo "用法: make pr-check PR=<编号> [REMOTE=gitee]"; exit 1; }
	@$(MAKE) --no-print-directory fetch-pr PR=$(PR) REMOTE=$(REMOTE)
	@git diff --quiet && git diff --cached --quiet \
		|| { echo "工作树有未提交改动，请先提交/暂存后再审查 PR"; exit 1; }
	@cur=$$(git symbolic-ref --short -q HEAD || git rev-parse --short HEAD); \
	trap 'git switch --quiet "$$cur" >/dev/null 2>&1 || true' EXIT INT TERM; \
	git switch --quiet pr/$(PR); \
	DIRS=$$( git -c core.quotepath=false diff --name-only $(REMOTE)/main...pr/$(PR) \
		| awk -F/ '$$1=="试卷" && NF>=3 {print $$1"/"$$2"/"$$3}' | sort -u ); \
	if [ -z "$$DIRS" ]; then echo "PR #$(PR) 未改动任何试卷目录，跳过试卷自查。"; \
	else for d in $$DIRS; do [ -f "$$d/Makefile" ] || continue; \
		echo "===== $$d : all（编译 TikZ + 两版）====="; \
		$(MAKE) -s -C "$$d" JOBS=1 all || exit 1; \
		echo "===== $$d : check ====="; \
		$(MAKE) -s -C "$$d" JOBS=1 check || exit 1; done; fi

# 抽样构建 + 全量自查（CI 入口；大规模时用 YEAR=… 限定）
ci:
	@echo "===== 工具单元测试 + 文档校验 ====="
	@python3 -m unittest tools.textfix.test_textfix tools.test_check_content tools.test_gen_index tools.test_json_to_tex tools.test_html2latex tools.test_check_formula_numbers tools.test_review_to_ledger \
    tools.test_check_meta tools.test_check_answers tools.test_check_units tools.test_tex_to_json tools.test_figsize_audit tools.test_figsize_tools
	@python3 tools/check_docs.py
	@echo "===== 抽样编译（首份试卷） ====="
	@d=$$(ls -d 试卷/*/* 2>/dev/null | head -1); \
	if [ -n "$$d" ] && [ -f "$$d/Makefile" ]; then $(MAKE) -s -C "$$d" JOBS=1 all; fi
	@echo "===== 全量自查（含文档索引） ====="
	@$(MAKE) --no-print-directory check

check-tikz:
	@$(OCRPIPE) check-tikz 试卷

check-recrop:
	@$(OCRPIPE) check-recrop 试卷

# 工具单元测试（共性问题修正 / 批量映射 / 裁剪 recipe / TikZ 登记 / 图片匹配 / 无损提图 / 裁剪回填）
tools-test:
	@echo "===== tools 单元测试 ====="
	@python3 -m unittest tools.textfix.test_textfix tools.test_check_content tools.test_gen_index tools.test_json_to_tex tools.test_html2latex tools.test_check_formula_numbers tools.test_review_to_ledger \
    tools.test_check_meta tools.test_check_answers tools.test_check_units tools.test_tex_to_json tools.test_figsize_audit tools.test_figsize_tools

# 材料处理管线（外部独立程序 OCRPipeLine；需 Conda 环境 / PaddleOCR-VL 服务）
material:
	@[ -n "$(PDF)" ] && [ -n "$(OUT)" ] || { \
		echo "用法: make material PDF=<源PDF> OUT=材料处理/<年>/<地区>"; exit 1; }
	$(OCRPIPE) run -c ocr_pipeline.json -i "$(PDF)" -o "$(OUT)" --auto-serve

# 全库/多卷一键编排（自动启停服务、断点续跑；参数经 ARGS 透传）
#   例：make material-batch ARGS="--only 2026/湖北"
#       make material-batch ARGS="--force"
material-batch:
	@$(OCRPIPE) batch -c ocr_pipeline.json --root 材料处理 $(ARGS)

material-merge:
	@$(OCRPIPE) merge --root 材料处理

extract-images:
	@$(OCRPIPE) images -c ocr_pipeline.json --root 材料处理

check-material:
	@$(OCRPIPE) check --root 材料处理

figsize-audit:
	@python3 tools/figsize_audit.py $(ARGS)

figsize-automap:
	@python3 tools/figsize_automap.py $(ARGS)

figsize-merge-fallback:
	@python3 tools/figsize_merge_fallback.py $(ARGS)

figsize-unit:
	@test -n "$(UNIT)" || { echo "用法：make figsize-unit UNIT=试卷/2026/北京 [ARGS='--force --skip-compile']"; exit 2; }
	@tools/figsize_unit.sh $(UNIT) $(ARGS)

figsize-fix-refs:
	@python3 tools/figsize_fix_refs.py $(ARGS)

figsize-plan:
	@python3 tools/figsize_plan.py $(ARGS)

figsize-apply:
	@python3 tools/figsize_apply.py $(ARGS)

figsize-check:
	@python3 tools/figsize_check.py $(ARGS)

figsize-status:
	@python3 tools/figsize_status.py $(ARGS)

figsize-review:
	@python3 tools/figsize_review.py $(ARGS)

figsize-check-ext:
	@test -n "$(UNIT)" || { echo "用法：make figsize-check-ext UNIT=试卷/2024/江西"; exit 2; }
	@$(OCRPIPE) figsize check $(UNIT) --manifest $(UNIT)/figures.manifest.json \
	  --auto-tolerance 0.05 --manual-tolerance 0.15 --strict --json

figsize-apply-ext:
	@test -n "$(UNIT)" || { echo "用法：make figsize-apply-ext UNIT=试卷/2024/江西 [ARGS=--write]"; exit 2; }
	@$(OCRPIPE) figsize apply $(UNIT) --manifest $(UNIT)/figures.manifest.json \
	  --no-unregistered --backup $(ARGS)

figsize-status-ext:
	@$(OCRPIPE) figsize status $(if $(ARGS),$(ARGS),试卷)

# ---------------------------------------------------------------------------
# OCR 流水线（外部独立程序 OCRPipeLine；OvisOCR3 + PaddleOCR-VL）
#   详见 OCR识别转换流程说明.md（软链接）
#   例：make ocr-status
#       make ocr-batch ARGS="--auto-serve --only 2026/湖北"
#       make OCRPIPE=/path/to/ocrpipe ocr-status
# ---------------------------------------------------------------------------
OCRPIPE ?= ocrpipe

ocr-plan:
	@$(OCRPIPE) plan -c ocr_pipeline.json --root 材料处理 $(ARGS)

ocr-status:
	@$(OCRPIPE) status -c ocr_pipeline.json --root 材料处理 $(ARGS)

ocr-batch:
	@$(OCRPIPE) batch -c ocr_pipeline.json --root 材料处理 $(ARGS)

links:
	@python3 tools/tex_links.py

clean:
	$(call RUN_DIRS,$(PAPERS),clean)

distclean:
	$(call RUN_DIRS,$(PAPERS),distclean)
