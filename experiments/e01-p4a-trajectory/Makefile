# E01 复现入口。每个阶段都可单独重跑；阶段间只通过 data/processed/e01/ 传递。
#
#   make setup     创建 .venv 并装依赖（主线阶段无第三方依赖，仅建环境）
#   make s0 s0b s1 s2  逐阶段
#   make all       s0 -> s0b -> s1 -> s2
#   make verify    带来源 md5 核算重扫一遍全语料（慢，约 350MB）
#   make smoke     只扫前 50 份，用于改完代码后的快速自检
#   make verify-stdlib  在无第三方依赖的隔离环境里跑主线，守住 dependencies = []

UV ?= uv
RUN = $(UV) run

.PHONY: setup setup-render s0 s0b s1 s2 s3 s4 dump all verify verify-stdlib smoke clean

OUT := ../../data/processed/e01

# 仓库根引入统一 workspace 后，环境只有一个（根 .venv），故 setup 委派给根。
# **不要**在本目录直接跑 `uv sync` —— 那会把 e01 当作活动项目，把根 dependency-group
# 里的 jupyter/pandas 从共享环境里剪掉。
setup:
	$(MAKE) -C ../.. setup

# 曾经是「只装 s3 需要的 jinja2 + tokenizers」。现在根的 setup 已 --all-extras，
# 两者等价，保留仅为兼容既有习惯。s0-s2「无第三方依赖也能跑」这条性质改由
# verify-stdlib 证明，不再靠"少装点东西"来体现。
setup-render: setup

s0:
	$(RUN) python -m e01.s0_manifest

# 把 systemPrompt 拆成块，给出每份 session 落在哪一类（约 10 秒）
s0b:
	$(RUN) python -m e01.s0b_prompt_blocks

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

all: s0 s0b s1 s2

verify:
	$(RUN) python -m e01.s0_manifest --verify-source
	$(RUN) python -m e01.s1_cache_fields

# stdlib-only 闸门。主线阶段（s0-s2、s4、s5）声明 `dependencies = []`，必须能在
# 没有网络、没有第三方包的机器上原样复现 —— 自从仓库根引入统一 workspace 之后，
# 共享 .venv 里装着 tokenizers/pandas 等包，`make smoke` 通过**不再能证明**这一点。
# 故这里用 uv 的临时隔离环境：只装 e01 自身（其 dependencies 为空），不碰共享 .venv。
#
# s0/s1/s2 的 --limit 写的是与全量同名的文件，直接跑会用 50 份的结果覆盖全语料产物，
# 所以先备份后还原；trap 保证中途失败也能还原。
verify-stdlib:
	@set -e; \
	tmp=$$(mktemp -d); \
	if [ -d "$(OUT)" ]; then cp -a "$(OUT)/." "$$tmp/" 2>/dev/null || true; fi; \
	trap 'cp -a "$$tmp/." "$(OUT)/" 2>/dev/null || true; rm -rf "$$tmp"' EXIT; \
	$(UV) run --isolated --no-project --with-editable . python -m e01.s0_manifest --limit 50; \
	$(UV) run --isolated --no-project --with-editable . python -m e01.s0b_prompt_blocks --limit 50; \
	$(UV) run --isolated --no-project --with-editable . python -m e01.s1_cache_fields --limit 50; \
	$(UV) run --isolated --no-project --with-editable . python -m e01.s2_session_stats --limit 50; \
	echo "stdlib-only OK: 主线阶段在无第三方依赖的隔离环境中跑通，产物已还原"

smoke:
	$(RUN) python -m e01.s0_manifest --limit 50
	$(RUN) python -m e01.s0b_prompt_blocks --limit 50
	$(RUN) python -m e01.s1_cache_fields --limit 50
	$(RUN) python -m e01.s2_session_stats --limit 50

clean:
	rm -rf ../../data/processed/e01
