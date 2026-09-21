# pi 启动配置

`default/` 提供一个可修改 system prompt 的最小配置。

在仓库根目录启动：

```bash
./pi-configs/default/start.sh
```

`default/SYSTEM.md` 初始内容取自本机 `@earendil-works/pi-coding-agent 0.85.1`
的原版默认 system prompt，使用默认的 `read/bash/edit/write` 工具组合。
这是可编辑的静态副本，包含本机 pi 文档路径；不会随 pi 升级或工具选择自动更新。

编辑 `default/SYSTEM.md`，下次启动时即使用新的内容。它替换 system prompt
的主体；工作目录、项目 `AGENTS.md` 和 skills 仍由 pi 动态追加。

模型、登录态、工具、扩展和会话配置沿用本机 pi。启动脚本保留调用时的
工作目录，并将额外参数原样传给 pi，例如：

```bash
./pi-configs/default/start.sh --thinking high
```

新增组合时，可复制 `default/` 为另一个目录，再修改其中的 `SYSTEM.md`
和 `start.sh`。
