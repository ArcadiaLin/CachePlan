# 仓库根入口。只做环境与仓库级约定；每个实验的流水线在各自目录的 Makefile 里。
#
#   make setup     建统一 uv 环境 + 装 nbstripout 的 git 过滤器（每个 clone 跑一次）
#   make lab       启动 JupyterLab
#   make verify    仓库级自检（E01、E06 的 stdlib-only 复现闸门）

UV ?= uv

.PHONY: setup lab verify hooks

setup: hooks
	$(UV) sync --all-packages --all-extras

# nbstripout 的过滤器命令写在 .git/config（本机，不进版本管理）；
# 哪些文件走过滤器写在 .gitattributes（跟踪）。两边缺一不可，故单列一个目标，
# 让"忘了装过滤器导致带输出的 notebook 被提交"这件事有个明确的补救入口。
#
# extrakeys 让过滤器额外剥掉 language_info.version：JupyterLab 打开 notebook 时
# 会把本机的 Python 补丁版号写进去，换机器或升补丁版就产生一行无意义的 diff。
# 它必须写进 git config —— nbstripout 每次运行时从 filter.nbstripout.extrakeys
# 读（_nbstripout.py:557），命令行的 --extra-keys 只对当次调用生效，不持久。
hooks:
	$(UV) run nbstripout --install --attributes .gitattributes
	git config filter.nbstripout.extrakeys "metadata.language_info.version"
	@echo "nbstripout git filter installed"

lab:
	$(UV) run jupyter lab

verify:
	$(MAKE) -C experiments/e01-p4a-trajectory verify-stdlib
	$(MAKE) -C experiments/e06-static-prefix verify-stdlib
