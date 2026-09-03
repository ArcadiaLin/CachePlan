# E06 的 Python 环境入口。统一 workspace 在仓库根；不要在本目录直接 uv sync。
#
#   make setup          委派根 workspace setup
#   make verify-stdlib  在隔离的无第三方环境中重跑 fixture 准备流水线

UV ?= uv

.PHONY: setup verify-stdlib

setup:
	$(MAKE) -C ../.. setup

# 四个准备脚本必须保持 stdlib-only。临时目录承载所有派生产物，故此验证不会
# 改写 data/processed/e06/；原始输入缺失时应失败，而不是从网络补取。
verify-stdlib:
	@set -e; \
	tmp=$$(mktemp -d); \
	trap 'rm -rf "$$tmp"' EXIT; \
	$(UV) run --isolated --no-project python src/build_fixture_manifest.py --output "$$tmp/fixture_manifest.json"; \
	$(UV) run --isolated --no-project python src/extract_external_evidence.py --output-root "$$tmp/evidence"; \
	$(UV) run --isolated --no-project python src/materialize_fixtures.py --fixture-manifest "$$tmp/fixture_manifest.json" --evidence-root "$$tmp/evidence" --output-root "$$tmp/fixtures"; \
	$(UV) run --isolated --no-project python src/recover_historical_judgments.py --output-root "$$tmp/expected"; \
	echo "stdlib-only OK: E06 fixture preparation ran in an isolated environment"
