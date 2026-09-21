---
name: pi-extension-dev
description: 开发 pi (pi-coding-agent) 的 extension，或在本项目的 pi-configs 下创建/修改 pi 启动配置版本。当用户要求编写、调试 pi extension，或管理 pi 配置时使用。
---

# pi Extension 开发

本 skill 不重复讲解如何开发 extension——本地 pi 源码仓库自带完整文档，开发时**直接引用这些文档**作为权威依据，不要凭记忆写 API。

## 权威文档（开发时必读）

主文档（extension API、事件、工具、UI，约 3000 行）：

- `~/projs/pi/packages/coding-agent/docs/extensions.md`

配套文档（按需查阅）：

- `~/projs/pi/packages/coding-agent/docs/custom-provider.md` — 自定义模型 provider
- `~/projs/pi/packages/coding-agent/docs/packages.md` — 把 extension 打包成 npm/git 包分发
- `~/projs/pi/packages/coding-agent/docs/tui.md` — TUI 组件 API（自定义渲染、overlay）
- `~/projs/pi/packages/coding-agent/docs/rpc.md` — RPC 模式与 extension UI 协议
- `~/projs/pi/packages/coding-agent/docs/session-format.md` — Session 存储与 SessionManager
- `~/projs/pi/packages/coding-agent/docs/keybindings.md` — 快捷键 id 列表

## 示例库

`~/projs/pi/packages/coding-agent/examples/extensions/` 下有 70+ 个可运行示例（hello、todo、permission-gate、plan-mode、ssh、subagent 等）。写新 extension 时优先找相近示例参考，不要从零发明结构。

## 加载与测试位置

- 项目级（推荐，跟随本项目）：`projs/CachePlan/.pi/extensions/`
- 全局（本项目不主动使用）：`~/.pi/agent/extensions/`
- 快速测试：`pi -e ./path.ts`
- 自动发现位置的 extension 支持 `/reload` 热重载

## 与本项目的关系：pi-configs 配置版本

本项目根目录有 `pi-configs/`，用于存放 pi 的启动配置版本（现有 `default/`）。约定见 `pi-configs/README.md`：

- 每个子目录是一套配置版本，含 `start.sh`（启动脚本，保留调用时 cwd，透传额外参数给 pi）和 `SYSTEM.md`（可编辑的静态 system prompt 副本，替换 prompt 主体；AGENTS.md 和 skills 仍由 pi 动态追加）
- 从仓库根目录用 `./pi-configs/<版本>/start.sh` 启动
- 新增配置版本：复制 `default/` 为新目录，修改其中的 `SYSTEM.md` 和 `start.sh`
- 模型、登录态、工具、扩展和会话配置沿用本机 pi

开发/调试 extension 时，如需隔离环境验证（自定义 system prompt、指定 extension 集合等），就在 `pi-configs/` 下新建一个配置版本来跑，不要改动 `default/` 或全局 `~/.pi/agent/` 的现役配置。
