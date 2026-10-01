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
#    make check        规范自查（各卷结构/元数据 + 内容 + 共性问题 + 版面命令 + TikZ 登记 + 裁剪 recipe + 材料完整性）
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
# ===========================================================================
PAPERS := 试卷/*/*

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
        clean distclean material material-merge extract-images check-material tools-test

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

check-tikz:
	@python3 tools/check_tikz.py

check-recrop:
	@python3 tools/check_recrop.py

# 工具单元测试（共性问题修正 / 裁剪 recipe / TikZ 登记 / 图片匹配 / 无损提图 / 裁剪回填）
tools-test:
	@echo "===== tools 单元测试 ====="
	@python3 -m unittest tools.textfix.test_textfix tools.test_check_recrop tools.test_check_tikz tools.test_match_figures tools.test_pdf_extract_images tools.test_recrop_figures

# 材料处理管线（需 Conda 环境 / PaddleOCR-VL 服务；详见 材料处理与OCR规范.md）
material:
	@[ -n "$(PDF)" ] && [ -n "$(OUT)" ] || { \
		echo "用法: make material PDF=<源PDF> OUT=材料处理/<年>/<地区>"; exit 1; }
	bash tools/ocr_pipeline.sh "$(PDF)" "$(OUT)"

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
