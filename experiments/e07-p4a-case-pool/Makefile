# E07 复现入口。阶段间只通过 data/processed/e07/ 传递。
#
#   make setup          委派给仓库根：建共享 .venv 并装 git 过滤器
#   make p0             筛出 961 观测集的 952 篇论文，复制 mineru/layer4/cite 三层数据
#   make p1             从 layer4/cite 建 paper–resource 边与引文锚点（套用消歧注册表）
#   make verify         重跑 p0 + p1（复制是幂等的：先清空再复制）
#   make verify-stdlib  在干净隔离环境里跑 p0+p1 小样（p0 保持 stdlib-only；
#                       隔离环境装上声明的 pyyaml，验证依赖清单自足）

UV ?= uv
RUN = $(UV) run

.PHONY: setup p0 p1 verify verify-stdlib clean

setup:
	$(MAKE) -C ../.. setup

p0:
	$(RUN) python -m e07.p0_select_observed_corpus

p1:
	$(RUN) python -m e07.p1_build_edges

verify: p0 p1

# 临时目录承载所有派生产物，故此验证不改写 data/processed/e07/；
# 原始输入（p4a-v1 副本、e01 观测集）缺失时应失败，而不是从网络补取。
verify-stdlib:
	@set -e; \
	tmp=$$(mktemp -d); \
	trap 'rm -rf "$$tmp"' EXIT; \
	$(UV) run --isolated --no-project --with-editable . \
		python -m e07.p0_select_observed_corpus --out-root "$$tmp/e07" --limit 20 && \
	$(UV) run --isolated --no-project --with-editable . \
		python -m e07.p1_build_edges --out-root "$$tmp/e07" --limit 20

clean:
	rm -rf ../../data/processed/e07
