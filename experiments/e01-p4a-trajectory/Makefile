# E01 复现入口。每个阶段都可单独重跑；阶段间只通过 data/processed/e01/ 传递。
#
#   make setup     创建 .venv 并装依赖（主线阶段无第三方依赖，仅建环境）
#   make s0 s1 s2  逐阶段
#   make all       s0 -> s1 -> s2
#   make verify    带来源 md5 核算重扫一遍全语料（慢，约 350MB）
#   make smoke     只扫前 50 份，用于改完代码后的快速自检

UV ?= uv
RUN = $(UV) run

.PHONY: setup setup-render s0 s1 s2 s3 s4 dump all verify smoke clean

setup:
	$(UV) sync

# s3 起需要 chat template + 分词器，见 README「分词器」一节
setup-render:
	$(UV) sync --extra render

s0:
	$(RUN) python -m e01.s0_manifest

s1:
	$(RUN) python -m e01.s1_cache_fields

s2:
	$(RUN) python -m e01.s2_session_stats

s3:
	$(UV) run --extra render python -m e01.s3_render

# 导出某份 session 的逐步上下文供肉眼查看：make dump SID=2d549e55
dump:
	$(UV) run --extra render python -m e01.s3_dump $(SID)

# --check 在 ground truth 上重新标定作废量公式（慢，约 3 分钟）
s4:
	$(UV) run --extra render python -m e01.s4_divergence --check

all: s0 s1 s2

verify:
	$(RUN) python -m e01.s0_manifest --verify-source
	$(RUN) python -m e01.s1_cache_fields

smoke:
	$(RUN) python -m e01.s0_manifest --limit 50
	$(RUN) python -m e01.s1_cache_fields --limit 50
	$(RUN) python -m e01.s2_session_stats --limit 50

clean:
	rm -rf ../../data/processed/e01
