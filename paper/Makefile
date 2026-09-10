# SIGMOD 投稿的编译入口。
#
#   make          编译 main.pdf（latexmk 自动跑够 pdflatex/bibtex 的轮数）
#   make check    校验 SIGMOD 的硬性限制：正文 ≤ 12 页、PDF ≤ 10 MB
#   make watch    盯着源文件改动持续重编
#   make clean    删掉中间文件，保留 main.pdf
#   make distclean 连 main.pdf 一起删
#
# 编译用的是 vendor/acmart/ 里的 acmart v2.20（2026-08-16），即 ACM 官网当前发的版本。
# 本机虽然装了 texlive-publishers，但 Debian 打包的是 v2.12（2024-12-28），差近两年，
# 不该拿它给 2027 年的会投稿。下面两行把 vendor 目录排在系统路径之前，vendor 因此胜出；
# 系统那份只在 vendor/ 缺失时兜底。路径结尾的冒号是必须的：它表示"再接着找系统默认路径"。
export TEXINPUTS := $(CURDIR)/vendor/acmart:
export BSTINPUTS := $(CURDIR)/vendor/acmart:

MAIN     ?= main
PAGELIMIT ?= 12
# 10 MB，CFP 规定的投稿 PDF 上限（末尾不能带行内注释，make 会把空格一起算进变量）
SIZELIMIT ?= 10485760

.PHONY: all check watch clean distclean

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex refs.bib
	latexmk -pdf -halt-on-error -interaction=nonstopmode $(MAIN).tex

# 论文用的 refs.bib 由仓库那份生成，不是第二份手维护的文献库。
# 剥掉 note 字段的理由见 tools/strip-notes.py 的注释：那是中文项目注解，
# ACM-Reference-Format.bst 会把它排进参考文献，pdflatex 直接编不过。
refs.bib: ../references/refs.bib tools/strip-notes.py
	python3 tools/strip-notes.py $< $@

watch:
	latexmk -pdf -pvc -interaction=nonstopmode $(MAIN).tex

# 页数从 main.aux 里 \label{endofbody} 的页码读，而不是数 PDF 总页数 ——
# 参考文献不计入 SIGMOD 的 12 页限制，所以总页数不是要卡的那个量。
check: $(MAIN).pdf
	@body=$$(sed -n 's/.*\\newlabel{endofbody}{{[^}]*}{\([0-9]*\)}.*/\1/p' $(MAIN).aux); \
	if [ -z "$$body" ]; then \
	  echo "FAIL: main.aux 里没有 endofbody 标签，正文页数无法核对"; exit 1; fi; \
	size=$$(stat -c %s $(MAIN).pdf); \
	echo "正文 $$body 页（上限 $(PAGELIMIT)），PDF $$size 字节（上限 $(SIZELIMIT)）"; \
	fail=0; \
	[ "$$body" -le $(PAGELIMIT) ] || { echo "FAIL: 正文超出 $(PAGELIMIT) 页"; fail=1; }; \
	[ "$$size" -le $(SIZELIMIT) ] || { echo "FAIL: PDF 超出 10 MB"; fail=1; }; \
	exit $$fail

clean:
	latexmk -c $(MAIN).tex

distclean:
	latexmk -C $(MAIN).tex
	rm -f refs.bib
