# E07 复现入口。阶段间只通过 data/processed/e07/ 传递。
#
#   make setup     委派给仓库根：建共享 .venv 并装 git 过滤器
#   make p0        筛出 961 观测集的 952 篇论文，复制 mineru/layer4/cite 三层数据
#   make verify    重跑 p0 的校验（复制是幂等的：先清空再复制）

UV ?= uv
RUN = $(UV) run

.PHONY: setup p0 verify clean

setup:
	$(MAKE) -C ../.. setup

p0:
	$(RUN) python -m e07.p0_select_observed_corpus

verify: p0

clean:
	rm -rf ../../data/processed/e07
