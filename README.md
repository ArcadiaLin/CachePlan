# CachePlan

A research codebase created to support an ongoing research project.

Not Ready to public release....

## Setup

```bash
make setup     # 建共享 .venv（Python 3.12）+ 装 nbstripout 的 git 过滤器
make lab       # 启动 JupyterLab
make verify    # 仓库级自检：主线阶段在无第三方依赖的隔离环境中仍能跑通
```

`make setup` 每个 clone 跑一次即可。它包含 `nbstripout --install`——过滤器命令写在
本机的 `.git/config`（不进版本管理），哪些文件走过滤器写在跟踪的 `.gitattributes`。
两边缺一不可，忘了装会导致带 cell 输出的 notebook 被提交；补救入口是 `make hooks`。

仓库根是一个 uv workspace，主线实验都是它的成员，共用一份 `uv.lock` 和一个 `.venv`。
`experiments/p4a`（历史项目，依赖冲突）与所有 TypeScript 目录不在其中。约定与理由见
[`AGENTS.md`](AGENTS.md) 的 *Environment and Notebooks* 一节。
