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
#    make check-material   材料四要素/图片引用/底稿漂移检查
#    make tools-test   运行 tools 单元测试（textfix / check_recrop / check_tikz / match_figures / pdf_extract_images / recrop_figures）
#    make links        为全部试卷目录创建指向根公共文件的软链接
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
        clean distclean material material-batch material-merge extract-images check-material tools-test \
        index progress check-docs check-changed ci

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
	@python3 tools/check_tikz.py
	@echo "===== 多子图裁剪 recipe 一致性检查 ====="
	@python3 tools/check_recrop.py
	@echo "===== 材料处理产物完整性检查 ====="
	@python3 tools/check_material.py
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

# 抽样构建 + 全量自查（CI 入口；大规模时用 YEAR=… 限定）
ci:
	@echo "===== 工具单元测试 + 文档校验 ====="
	@python3 -m unittest tools.textfix.test_textfix tools.test_ocr_batch tools.test_check_content tools.test_check_recrop tools.test_check_tikz tools.test_match_figures tools.test_pdf_extract_images tools.test_recrop_figures tools.test_gen_index tools.test_json_to_tex tools.test_html2latex tools.test_check_formula_numbers tools.test_review_to_ledger \
    tools.test_check_meta tools.test_check_answers tools.test_check_units tools.test_tex_to_json
	@python3 tools/check_docs.py
	@echo "===== 抽样编译（首份试卷） ====="
	@d=$$(ls -d 试卷/*/* 2>/dev/null | head -1); \
	if [ -n "$$d" ] && [ -f "$$d/Makefile" ]; then $(MAKE) -s -C "$$d" JOBS=1 all; fi
	@echo "===== 全量自查（含文档索引） ====="
	@$(MAKE) --no-print-directory check

check-tikz:
	@python3 tools/check_tikz.py

check-recrop:
	@python3 tools/check_recrop.py

# 工具单元测试（共性问题修正 / 批量映射 / 裁剪 recipe / TikZ 登记 / 图片匹配 / 无损提图 / 裁剪回填）
tools-test:
	@echo "===== tools 单元测试 ====="
	@python3 -m unittest tools.textfix.test_textfix tools.test_ocr_batch tools.test_check_content tools.test_check_recrop tools.test_check_tikz tools.test_match_figures tools.test_pdf_extract_images tools.test_recrop_figures tools.test_gen_index tools.test_json_to_tex tools.test_html2latex tools.test_check_formula_numbers tools.test_review_to_ledger \
    tools.test_check_meta tools.test_check_answers tools.test_check_units tools.test_tex_to_json

# 材料处理管线（需 Conda 环境 / PaddleOCR-VL 服务；详见 材料处理与OCR规范.md）
material:
	@[ -n "$(PDF)" ] && [ -n "$(OUT)" ] || { \
		echo "用法: make material PDF=<源PDF> OUT=材料处理/<年>/<地区>"; exit 1; }
	bash tools/ocr_pipeline.sh "$(PDF)" "$(OUT)"

# 全库/多卷一键编排（五阶段，失败即停、断点续跑；参数经 ARGS 透传）
#   例：make material-batch ARGS="--year 2026"
#       make material-batch ARGS="--force"
material-batch:
	@bash tools/ocr_pipeline_all.sh $(ARGS)

material-merge:
	@python3 tools/material_merge.py --root 材料处理

extract-images:
	@python3 tools/pdf_extract_images.py --root 材料处理

check-material:
	@python3 tools/check_material.py

links:
	@python3 tools/tex_links.py

clean:
	$(call RUN_DIRS,$(PAPERS),clean)

distclean:
	$(call RUN_DIRS,$(PAPERS),distclean)
