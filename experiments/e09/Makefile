# E09 入口。目前只有环境目标，还没有流水线阶段目标（pN）。
#
#   make setup       委派给仓库根：建共享 .venv 并装 git 过滤器
#   make neo4j-up    启动 infra/neo4j-e09（bolt 7687，浏览器 7474；先停 neo4j-e08）
#   make neo4j-down  停止 neo4j-e09（数据保留在 infra/neo4j-e09/data/）
#   make check       环境自检：材料与种子目录、连库、版本与 edition、确认不是 v1 库
#   make lab         在本目录启动 JupyterLab
#
# 当前用户若不在 docker 组：make neo4j-up DOCKER="sudo docker"

UV ?= uv
DOCKER ?= docker
RUN = $(UV) run
COMPOSE = $(DOCKER) compose -f ../../infra/neo4j-e09/docker-compose.yml

.PHONY: setup neo4j-up neo4j-down check lab clean

setup:
	$(MAKE) -C ../.. setup

neo4j-up:
	$(COMPOSE) up -d

neo4j-down:
	$(COMPOSE) down

check:
	$(RUN) python -m e09.env_check

lab:
	mkdir -p notebooks && $(RUN) jupyter lab --notebook-dir=notebooks

clean:
	rm -rf notebooks/_scratch
