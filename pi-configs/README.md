# pi 启动配置

每个子目录是一套配置，包含自己的 system prompt、extensions 和 session 记录：

```text
pi-configs/<版本>/
├── start.sh
├── SYSTEM.md
├── extensions/       # 在这里开发该配置的扩展，纳入 Git
└── sessions/         # pi 自动创建并持久化对话，Git 忽略
```

在仓库根目录启动：

```bash
./pi-configs/default/start.sh
```

`default/SYSTEM.md` 初始内容取自本机 `@earendil-works/pi-coding-agent 0.85.1`
的原版默认 system prompt，使用默认的 `read/bash/edit/write` 工具组合。
这是可编辑的静态副本，包含本机 pi 文档路径；不会随 pi 升级或工具选择自动更新。

编辑 `default/SYSTEM.md`，下次启动时即使用新的内容。它替换 system prompt
的主体；工作目录、项目 `AGENTS.md` 和 skills 仍由 pi 动态追加。

模型、登录态和内置工具配置沿用本机 pi。启动脚本保留调用时的工作目录，
用 `--session-dir` 将对话写入当前配置的 `sessions/`，并透传额外参数，例如：

```bash
./pi-configs/default/start.sh --thinking high
./pi-configs/default/start.sh --continue
./pi-configs/default/start.sh --resume
```

`--continue` 继续该配置下、当前工作目录的最近会话，`--resume` 打开会话选择器。
这些默认路径可由显式传入的 pi 参数覆盖。

扩展放在该配置的 `extensions/` 中，可以是 `my-extension.ts`，
也可以是 `my-extension/index.ts`。启动脚本使用 `--no-extensions --extension <配置目录>`，
按 pi 本地资源包规则加载该目录中的扩展；全局和项目 `.pi/extensions/`
不会自动加载。需要额外扩展时可以显式传入 `-e /path/to/extension.ts`。
修改或新增配置内扩展后，在 pi 中用 `/reload` 重新加载。

配置目录也支持 pi 资源包约定的 `skills/`、`prompts/` 和 `themes/`；
这些资源会额外加载，原有全局和项目资源仍按 pi 的规则发现。

新增配置时，创建新目录及其中的 `extensions/`（没有扩展时也保留空目录），
复制 `default/start.sh`、`default/SYSTEM.md` 和需要的扩展源码；不要复制 `sessions/` 历史记录。
启动脚本会根据自身位置选择新配置的资源和会话目录。

## no-write-bash

`no-write-bash/` 在通用结构之上做了两处调整：

- 启动脚本加 `--exclude-tools write,bash`，禁用内置的 write 和 bash 工具
  （保留 read、edit），`SYSTEM.md` 也相应改写，可继续自由编辑。
- 启动脚本设置 `PI_CODING_AGENT_DIR=<配置目录>/agent`，使模型配置来自该目录下
  自己的 `models.json`（纳入 Git）。pi 没有单独的 models.json 路径参数，只能整体
  重定向 agent 目录；因此 `agent/` 下的 `auth.json`、`settings.json`、`trust.json`
  和 `skills/` 是指向 `~/.pi/agent/` 同名条目的符号链接，登录态、设置和全局 skills
  仍沿用本机 pi。这些符号链接和 pi 生成的缓存（`models-store.json`、`npm/` 等）
  被 `.gitignore` 排除，只有 `models.json` 入库。
