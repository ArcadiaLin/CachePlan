# E01 复现入口。每个阶段都可单独重跑；阶段间只通过 data/processed/e01/ 传递。
#
#   make setup     创建 .venv 并装依赖（主线阶段无第三方依赖，仅建环境）
#   make s0 s1 s2  逐阶段
#   make all       s0 -> s1 -> s2
#   make verify    带来源 md5 核算跑一遍闸门（慢，约 350MB）
#   make smoke     只扫前 50 份，用于改完代码后的快速自检

UV ?= uv
RUN = $(UV) run

.PHONY: setup s0 s1 s2 all verify smoke clean

setup:
	$(UV) sync

s0:
	$(RUN) python -m e01.s0_manifest

s1:
	$(RUN) python -m e01.s1_cache_fields

s2:
	$(RUN) python -m e01.s2_session_stats

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
