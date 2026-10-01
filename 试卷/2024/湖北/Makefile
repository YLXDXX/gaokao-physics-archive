# ===========================================================================
#  高考试卷构建（模板；每份试卷目录一份，内容相同，仅随目录层级改变 ROOT）
#
#  用法：
#    make            编译本卷（TikZ 图片 + 正文 PDF）
#    make all        同上
#    make tikz       仅编译 TikZ/ 下的独立图片（生成 PDF）
#    make tikz-compare 生成「重绘 TikZ 与原图」对比图（tikz_compare/，需先登记 TikZ/tikz_sources.json）
#    make check      规范自查（元数据字段/图片引用/标注一致等）
#    make links      创建/更新指向项目根公共文件（文档类/宏包）的软链接
#    make clean      清理辅助文件
#    make distclean  清理辅助文件与 PDF 成品
#
#  公共文件（gaokaozhenti.cls / PhyUnit.sty / ChoiceQuestion.sty / package/）
#  位于项目根目录，通过 TEXINPUTS 引入，并在本目录建立指向根目录的相对软链接
#  （make links），无需复制到本目录。
#
#  并行：本目录内多个文档相互独立，按 JOBS 并行。JOBS 默认 1（串行）；
#        可用 make JOBS=8 指定线程数，也可用 make -j8（取 -jN 的 N）。
# ===========================================================================
ROOT     := ../../..
export TEXINPUTS := $(ROOT):
# svg 宏包需调用 Inkscape，故开启 shell-escape
LATEXMK  := latexmk -xelatex -shell-escape -interaction=nonstopmode -halt-on-error

ifeq ($(origin JOBS),undefined)
JOBS := 1
_JN := $(patsubst -j%,%,$(filter -j%,$(MAKEFLAGS)))
ifneq ($(_JN),)
JOBS := $(_JN)
endif
endif
XARGS := xargs -0 -r -n1 -P $(JOBS)

SRC  := $(wildcard *.tex)
BASE := $(basename $(SRC))

.PHONY: all tikz tikz-compare check links clean distclean

all: tikz
	@$(MAKE) --no-print-directory compile

compile:
	@for d in $(BASE); do printf '%s\0' "$$d"; done \
		| $(XARGS) sh -c 'd="$$1"; echo ">> 编译 $$d"; \
			$(LATEXMK) -jobname="$$d" "$$d.tex" >"$$d.make.log" 2>&1 \
			|| { echo "!! $$d 编译失败，详见 $$d.make.log"; tail -30 "$$d.make.log"; exit 1; }' sh \
		|| exit 1

TIKZ_SRC := $(wildcard TikZ/*.tex)

tikz:
	@for t in $(TIKZ_SRC); do p="$${t%.tex}.pdf"; { [ -f "$$p" ] && [ "$$p" -nt "$$t" ]; } || printf '%s\0' "$$t"; done \
		| $(XARGS) sh -c 'echo ">> 生成 TikZ 图片 $$1"; \
			$(LATEXMK) -outdir=TikZ "$$1" >"$${1%.tex}.tikz.log" 2>&1 \
			|| { echo "!! $$1 编译失败，详见 $${1%.tex}.tikz.log"; tail -20 "$${1%.tex}.tikz.log"; exit 1; }' sh \
		|| exit 1

check:
	@for d in $(BASE); do \
		echo ">> 规范自查：$$d"; \
		python3 "$(ROOT)/tools/check_paper.py" "$$d.tex" || exit 1; \
	done

# 生成「重绘 TikZ 与原图」对比图（tikz_compare/，供人工核对；见 tools/tikz_compare.py）
#   先在 TikZ/tikz_sources.json 登记每张 TikZ 对应的原图
tikz-compare:
	@python3 "$(ROOT)/tools/tikz_compare.py" .

links:
	@python3 "$(ROOT)/tools/tex_links.py" .

clean:
	rm -f *.aux *.log *.out *.toc *.synctex.gz *.fls *.fdb_latexmk *.make.log
	rm -f TikZ/*.aux TikZ/*.log TikZ/*.out TikZ/*.xdv TikZ/*.fls TikZ/*.fdb_latexmk *.tikz.log

distclean: clean
	rm -f *.pdf
	rm -f TikZ/*.pdf
