# E08 入口。目前只有探索面，还没有流水线阶段目标（pN）。
#
#   make setup   委派给仓库根：建共享 .venv 并装 git 过滤器
#   make lab     在本目录启动 JupyterLab（notebook 里自己向上找仓库根）
#   make clean   删掉 notebook 旁的探索产物（不在版本管理内）
#
# 还没有 verify / verify-stdlib：E08 声明了第三方依赖（beautifulsoup4），
# 不需要 stdlib-only 闸门；等有了 pN 脚本再加可失败的复现目标，
# 并把它挂到根 Makefile 的 verify 上。

UV ?= uv
RUN = $(UV) run

.PHONY: setup lab clean

setup:
	$(MAKE) -C ../.. setup

lab:
	$(RUN) jupyter lab --notebook-dir=notebooks

clean:
	rm -rf notebooks/_scratch
