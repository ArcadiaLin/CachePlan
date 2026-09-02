---
name: develop-widi-extension
description: 在 CachePlan 中开发、修改或调试 WIDI extension；覆盖 Core/TUI 双入口、工具、provider、profile、拦截器、观察器、命令、快捷键、组件和 extension event bus，并规定与固定 WIDI submodule 的边界、验证与常见陷阱。
---

# 在 CachePlan 中开发 WIDI extension

本仓库通过 `packages/widi/` Git submodule 使用一个固定 revision 的 WIDI runtime；可比较的 WIDI 版本由 `widis/.widi-<variant>/` 下独立的 agent-dir 配置组装。WIDI extension 使用 WIDI 自己的运行时协议，**不是** Pi coding-agent 的 `ExtensionAPI`。不要使用 Pi 文档中的 `pi.registerTool()`、`pi.on()` 等 API；必须遵守当前固定 WIDI revision 的 Core/TUI 契约。

WIDI runtime 是可演化的个人项目。需要新的通用 runtime 能力时，在 `packages/widi` 对应仓库中提交该改动，再更新父仓库 gitlink；不要复制、重命名或向父仓库引入第二份 runtime。比较 WIDI revision 时，分别以每个 gitlink revision 完整运行同一组 `widis/.widi-<variant>/` 配置，并在实验 manifest 中记录 revision。

研究工作流的领域逻辑、工具和编排应放在父仓库的、按配置变体隔离的项目级 extension 中。`packages/widi/` 只提供通用运行时能力；除非公开 extension API 经最小复现证明无法表达所需的通用能力，否则不要修改 submodule 源码。

## 0. 写代码前必须读取

按此顺序读取，不要凭记忆写 API：

1. `packages/widi/apps/widi/docs/extensions.md`：当前固定 revision 的 extension 合约与发现规则。
2. `packages/widi/apps/widi/src/core/extension/api.ts`：extension 作者可依赖的 Core 导出面。
3. `packages/widi/apps/widi/src/core/extension/types.ts`：`ExtensionActivationApi`、`ExtensionContext`、`ExtensionActions`、拦截器和观察事件的完整签名。
4. `packages/widi/apps/widi/src/tui/extension-host/types.ts`：`WidiTuiExtensionApi` 和 TUI 类型。
5. `packages/widi/.widi/extensions/drill/`：上游双入口行为基准；只作参考，不能作为 CachePlan extension 的落点。
6. 根目录 `AGENTS.md` 和 `packages/widi/AGENTS.md`：本仓库研究约束与 WIDI submodule 规则。

Extension 只能依赖 `packages/widi/apps/widi/src/core/extension/api.ts` 及其中明确重导出的公共类型，以及 TUI host 的公开类型。禁止导入 `orchestrator`、`loader`、`runner` 或其他 WIDI 内部实现，也不要保存内部 runtime 对象。

## 1. 先确定入口形态

| 需求 | 入口 |
| --- | --- |
| 工具、模型 provider、profile、system prompt、拦截器、观察器、session state、agent 事件 | Core half：default export；每个 agent runtime 激活一次 |
| slash command、快捷键、widget/layout、tool/message renderer、theme、editor 文本 | TUI half：具名 `tui` export；整个应用激活一次 |
| 两者都需要 | 双入口；通过 extension event bus 通信 |

只需要一半时只实现一半，不要为了对称增加空的另一半。需要独立评测的确定性算法保持纯净边界：使用显式输入输出和注入的 provider、cache、clock；extension 仅负责适配和编排。

## 2. 按 WIDI 配置变体隔离落点、发现与 scaffold

每个实验 arm 或 WIDI 组装变体都必须有独立、可复现的 agent dir：

```text
packages/
└── widi/                           # 所有配置共享的固定 runtime gitlink
widis/
├── .widi-<variant-a>/
│   ├── settings.json
│   ├── profiles/
│   ├── prompts/
│   ├── skills/
│   └── extensions/
└── .widi-<variant-b>/
    ├── settings.json
    ├── profiles/
    ├── prompts/
    ├── skills/
    └── extensions/
```

`<variant>` 是实验清单和启动命令共用的稳定配置标识，不是 WIDI branch 或 submodule 路径。每个实验记录必须同时给出 `packages/widi` 的 gitlink revision、`widis/.widi-<variant>/` 路径、配置文件 digest 及实际启动命令。禁止在一次比较中让两个变体共享 agent dir，或让运行回退到 WIDI submodule 自己的 `.widi/` 配置；否则 extension、profile、prompt 或设置漂移会污染消融结论。

运行每个变体时，启动封装必须从 `packages/widi/` runtime 启动并显式传入 `--agent-dir widis/.widi-<variant>`。不要把项目 extension 写入 `packages/widi/.widi/extensions/`；那是 submodule 自己的配置与 `drill` 示例，不属于父仓库的实验配置。

extension id 是入口文件名或目录名。扩展只属于一个变体时，落在：

```text
widis/.widi-<variant>/extensions/<id>/
├── index.ts        # default Core export；需要 TUI 时再导出 named tui
├── protocol.ts     # 双入口才需要：事件名和 JSON payload 类型
├── core/           # Core half
├── tui/            # TUI half
└── tsconfig.json
```

需要跨变体比较的 extension 必须在每个变体 agent dir 中保有明确副本或通过已记录的共享源路径加载；不得通过未记录的软链接、默认发现路径或 home agent dir 隐式共享。跨变体的共同逻辑应是可审计的纯模块，变体专属适配层留在各自 extension 目录。

入口按 `package.json` 的 `widi.extensions`（兼容 `pi.extensions`）第一项解析，否则按 `index.ts`、`index.js`、`index.mjs`、`index.cjs` 解析。入口由 jiti 动态加载，TypeScript 不需要预编译。

从项目级 extension 到 WIDI 作者 API 的相对导入路径取决于 agent dir 的实际目录深度。必须在创建时计算并类型检查；不得复制其他变体或 `drill` 的相对路径：

```ts
import {
	EXTENSION_API_VERSION,
	type ExtensionDefinition,
} from "<relative>/packages/widi/apps/widi/src/core/extension/api.ts";
import type { TuiExtensionModule } from "<relative>/packages/widi/apps/widi/src/tui/extension-host/index.ts";
```

`apiVersion` 使用 `EXTENSION_API_VERSION`，不要自行写版本常量。`tsconfig.json` 应继承 `packages/widi/tsconfig.base.json`，并为 `@arcadialin/agent-core` 配置指向该 submodule 的路径映射；路径同样必须按实际深度计算。

在该变体的 agent dir 的 `settings.json` 中启用：

```json
{
	"enabledExtensions": ["<id>"]
}
```

`enabledExtensions` 存的是 id，不是路径；不设置该键表示加载全部发现的 extension，空数组表示不加载任何 extension。`extensions` 是显式入口路径，不能与 `enabledExtensions` 混淆。

## 3. Core half

`activate(api)` 只声明贡献，不是当前 agent 的操作上下文。注册工作放在这里，运行时动作放进 handler。可用能力包括 `registerTool`、`patchTool`、`registerProvider`、`registerProfile`、`appendSystemPrompt`、`observe`、`intercept`、`onExtensionEvent`、`onDispose` 和 `division`。

核心约束：

- 工具失败必须 `throw`，不能用成功返回值伪造错误。
- 工具自行限制输出大小，避免无界内容进入模型上下文。
- 执行工作前检查 abort signal。
- 文件路径基于运行 agent 的 workspace cwd，不能用捕获的 `process.cwd()` 替代。
- `details` 放结构化日志或 presenter 数据，不必复制模型可见文本。
- 工具可能并行执行；读改写同一文件时必须处理竞争。
- 修改既有工具用 `patchTool()`；不要注册隐式替代工具。

observer、interceptor 和 bus handler 收到 `ExtensionContext`。运行时操作只能走 `context.actions` 和 `context.session`，不要将这些上下文保留到 dispose 或 reload 之后。

发送文本的语义不可混用：

- `prompt`：目标必须 idle；忙时拒绝，不排队。
- `steer`：插入当前运行。
- `followUp`：当前任务结束后再运行。
- `precede`：写入 branch，下一轮模型可见，但不唤醒 agent。

四者都会再次经过 `input` interceptor。`context.session.appendEntry()` 会持久化、在 resume 重放、在 fork 复制且不能删除；只有恢复、分叉或审计确实需要的状态才写入，普通缓存保留在内存或外部可控存储。

## 4. TUI half 与双入口通信

TUI command 必须声明 `kind`、`agentPolicy`、`name`、`description` 与 action 的 `execute` 或 prompt 的 `expand`。快捷键注册使用 binding id；真实 action id 是 `ext.<extensionId>.<bindingId>`，用户可通过 `keybindings.json` 覆盖按键。

TUI half 不绑定某一个 agent。驱动当前可见 agent 使用 capability，或由 TUI 发出 event bus 事件并由 Core runtime 执行。`stage(text)` 只将文本放进 editor，不保证写入 session 或被模型读取。组件和 renderer 必须容忍失败。

Core 与 TUI 绝不互相 import。共享内容只放纯数据模块；事件定义放在 `protocol.ts`。事件名使用 `<owner>:<event>`，payload 必须是可复制冻结的 JSON value。总线会广播给所有 live Core runtime 和 TUI subscriber，包括发送者自身；handler 应检查来源并避免无条件互相回应。

## 5. 常见错误

- 不要在 `tool_call` 或 `context` interceptor 中 `await waitForIdle()`；当前 turn 等待 interceptor 返回，会死锁。
- `input` interceptor 同时收到人类、agent、runtime 和 extension 注入消息；只针对人类输入时检查 `event.source`。
- `input` 与 `tool_call` handler fail-closed；其他 hook 记录诊断并继续。
- observed event 无顺序保证；可能先收到状态事件，后收到 spawned 事件。
- `registerProvider` 是 first-registration-wins；同 id 的用户 profile 会遮蔽 extension profile。
- division 必须同时出现在声明和注册逻辑中；禁用祖先会硬禁用子 division。
- `onDispose` 必须释放 timer、watcher、连接等长生命周期资源。
- 不要把 API key、cookie、代理凭据写入 extension；从环境变量或忽略的本地状态读取，网络调用设置 timeout、有界重试与可观测错误。

## 6. 验证闭环

首次使用 WIDI 环境时，在 submodule 内执行：

```bash
npm ci
```

对每个配置变体的项目级 extension 单独类型检查与格式检查。将 `<extension-dir>` 替换为实际落点：

```bash
npm --prefix packages/widi exec -- tsgo --noEmit -p <extension-dir>/tsconfig.json
npm --prefix packages/widi exec -- biome check --config-path packages/widi/biome.json <extension-dir>
```

动态加载的 extension 不被 WIDI workspace 的 `npm run check` 自动覆盖，上述检查不可省略。修改 Core half 后在目标变体 TUI 输入 `/reload`；修改 TUI half 后重启该变体的 TUI。必须从 `packages/widi/` runtime 以显式 `--agent-dir widis/.widi-<variant>` 启动实际 surface 验证，不要以裸 `npm run tui`、抓取 TUI 文本或直接读取 session 文件替代。

排查顺序：确认目标配置变体、agent dir 和 `enabledExtensions`；查看启动或 `/reload` 诊断中的 `extension.load_failed`、`extension.version_incompatible`、`extension.activation_failed`；检查 division；重启目标 TUI；最后与 `packages/widi/.widi/extensions/drill/` 和 `packages/widi/apps/widi/docs/extensions.md` 对照。

## 7. 交付前检查

- [ ] extension 位于配置的项目级发现路径，且所用 agent dir 已启用其 id。
- [ ] 仅依赖公开 Core/TUI 作者 API。
- [ ] `core/` 与 `tui/` 没有互相 import；共享内容是纯数据。
- [ ] `apiVersion` 使用 `EXTENSION_API_VERSION`，声明的 division 都实际注册贡献。
- [ ] 所有长生命周期资源在 `onDispose` 释放。
- [ ] 工具失败时抛错，输出有界，并检查 abort signal。
- [ ] 没有无理由的 session branch 写入；若写入，说明恢复、fork 或审计为何需要它。
- [ ] 领域逻辑没有下沉到 WIDI submodule；网络、缓存和时钟边界可注入且错误可观察。
- [ ] extension 的 `tsgo`、Biome 检查通过，并在配置它的 WIDI surface 中实际运行过。
