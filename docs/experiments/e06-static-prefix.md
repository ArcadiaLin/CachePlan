# E06 — Static-prefix baseline：P4A-derived WIDI 重执行

**状态：计划中。** 这是 CachePlan 的第一个受控实验，不是对历史 P4A/Kimi 运行的重放。它在固定 WIDI runtime、模型服务、工具 schema 和冻结输入上，比较可复用 skill 的三种 placement。P4A 历史 session 只提供真实任务样本、轨迹特征和选样框；结论来自新的 WIDI 运行。

**前置闸门：** E01 s3 的精确 prompt 复现及其三段 token 分解必须验收。E01 的历史 cache 字段恒为 0，是旧 provider 上报缺陷；E06 必须通过 vLLM 0.22.1 的 `cached_tokens` 直接取得真实逐请求命中数据。见 [`e01-p4a-trajectory.md`](e01-p4a-trajectory.md) §2–4。

## 1. 研究问题与边界

E06 回答 OQ2 的第一部分：

> 对于每个 run 都需要同一份 procedural skill 的数据处理 agent workflow，直接把该 skill 放到 system prompt 的稳定前缀中，是否已经足以消除动态 skill loading 的主要重复 prefill？

本实验比较的不是历史 Kimi 与 WIDI，也不直接验证未来 CachePlan 方法。它先建立本项目必须击败的强 baseline：

$$
\text{tools} \rightarrow \text{skill} \rightarrow \text{per-case content}.
$$

P4A 的用途受以下边界约束：

- 历史 P4A 日志和既有工程保持只读、不可变。
- 选取的 P4A case 会被 fixture 化后由 WIDI 重新执行；历史 token/cost 不作为本实验对照数据。
- 第一轮只覆盖 P4A Layer-4 resource judgment / validation slice，而不是完整外部网络检索流水线。
- 结论应表述为 P4A-derived workload 上的受控结果，不外推为所有 agent workload 的结论。

详见 [`p4a.md`](p4a.md) §2–4。

## 2. 固定 WIDI runtime，隔离 WIDI 配置变体

`packages/widi/` 是本项目唯一的 WIDI runtime submodule。它是可演化的个人项目：需要新的 runtime 行为时，在 WIDI 仓库中提交该变更，再由父仓库更新 `packages/widi` 的 gitlink。每次实验运行都必须记录该 gitlink revision；同一 E06 对比中的所有 arm 必须使用完全相同的 revision。

E06 的可比版本不通过复制或重命名 runtime 构造，而是通过独立 agent dir 组装：

```text
packages/
└── widi/                            # 固定 gitlink 的 WIDI runtime

widis/
├── .widi-e06-a0-dynamic/
├── .widi-e06-a1-naive/
└── .widi-e06-a2-static-first/
```

这些目录是 placement 配置变体：它们分别拥有 settings、profile、skill、extension 配置和显式启动命令，但共享同一份 `packages/widi/` runtime。任何 WIDI runtime 修改都是另一条消融轴；比较两个 revision 时，对每个 revision 分别完整运行 A0/A1/A2，并以 gitlink revision 区分结果。不得在单次 A0/A1/A2 对比中混用 WIDI revision。

A3 暂不配置；它只能在 CachePlan 方法具体化后，作为叠加在 A2 上的处理臂出现。

## 3. 处理臂

三臂共享 provider、模型、WIDI revision、tokenizer/chat template、工具 schema、fixture、case 顺序和运行协议。唯一变量是 canonical skill body 与 case-specific 内容的 prompt 顺序。

| Arm | Agent dir | Prompt layout | 作用 |
| --- | --- | --- | --- |
| A0 | `.widi-e06-a0-dynamic` | `tools → common prompt → task-specific user prompt → dynamic skill read` | 当前两跳 dynamic loading 的现实 baseline |
| A1 | `.widi-e06-a1-naive` | `tools → variable case block → static skill` | 验证“静态但位于分叉点之后”仍无法复用 |
| A2 | `.widi-e06-a2-static-first` | `tools → static skill → task-specific user prompt` | 必须击败的强 static-prefix baseline |

### A0 — Dynamic skill loading

A0 提供 canonical P4A-WIDI skill 的路径和短指令：每个任务必须先通过 `read` 工具读取该 skill，再遵循其流程执行。`paper_id`、fixture 路径或任务说明必须保留在每个 run 不同的 user prompt 中。

这是历史 P4A 的关键结构：首个模型请求已看到 per-paper 信息，随后才加载 skill。因此跨 run 的 cache prefix 在 skill body 之前断裂。不能把任务改成“处理当前目录中的任意 paper”，否则会人为移动分叉点并测得另一个问题。

### A1 — Naive static placement

A1 使用与 A2 字节完全相同的 skill body，但 layout extension 将 per-case metadata 放到它之前：

```text
tools
case metadata / paper id / case manifest
skill body
```

A1 是 placement 反例，不是主要 quality baseline。它隔离“静态注入”与“静态内容位于稳定前缀”的差别。

### A2 — Static-first placement

A2 将相同 canonical skill 放在 tools 之后、用户任务之前：

```text
tools
skill body
user task for paper <paper-id>
```

未来方法的增量只能相对 A2 报告：

$$
\Delta_{\mathrm{method}} = A3 - A2,
$$

不能以 $A3-A0$ 作为 CachePlan 方法贡献。

## 4. Agent-dir 与配置不变量

每个 arm 的 agent dir 采用相同骨架：

```text
widis/.widi-e06-a*/
├── settings.json
├── profiles/
│   └── p4a-extract.md
├── skills/
│   └── p4a-resource-extract/
│       └── SKILL.md
├── extensions/                     # 或 settings.json 显式引用共同源码
└── e06-layout.json                 # 该 arm 的唯一布局参数
```

共同不变量：

- canonical skill body 只维护一个受版本控制的源；复制时必须记录并验证 SHA-256。
- 每个 run manifest 记录 runtime gitlink、profile、skill、extension、tool schema、fixture manifest 的 digest。
- profile 默认设置 `projectContext: false`、`includeCwd: false`、`skillsListing: false`。任何例外必须成为显式实验变量；工作目录、项目 context 或自动 skill listing 不得暗中进入 system prompt。
- 单 agent、禁止 delegation。child agent 的 id、profile 和工具状态会引入额外不稳定前缀。
- 所有启动命令必须显式传入对应 `--agent-dir`；不得回退到 WIDI runtime submodule 内的 `.widi/`。

## 5. 共同 extension

所有臂加载相同 extension 集与相同版本。arm 行为由 agent-dir 中的显式配置决定，而不是通过不同 extension schema 实现。

### `e06-layout`

唯一职责是构造三种 prompt layout：

- A0 不插入 skill body，只暴露 dynamic skill path；
- A1 将 case-specific block 置于 skill body 前；
- A2 将 skill body 置于 tools 后、易变 case 内容前。

它可以使用 `appendSystemPrompt()` 和必要时的 `before_agent_start` interceptor，但不得注册业务工具、修改任务语义或写入 telemetry。

### `e06-fixture-tools`

将 P4A judgment 阶段需要的本地脚本封装成固定、可审计且输出有界的工具：

- `p4a_apply_judgment`：只对当前 case 的 `agent_judgment.json` 执行既定 merge。
- `p4a_validate_outputs`：只运行既定 validator，返回结构化结果。
- `p4a_lookup_evidence`：仅当 fixture 需要时启用；只访问 case 内冻结的 GitHub/HuggingFace/arXiv 证据。

这些工具替代通用 shell 命令，避免命令措辞、任意外部访问和无关的工具轨迹成为变量。

### `e06-telemetry`

只观测，不干预。通过 `agent_harness_event` 或 provider trace 写入 session 外的 append-only JSONL；不得调用 `context.session.appendEntry()`，后者会污染后续 prompt。

每个请求至少记录：

```text
run_id, runtime_id, arm, case_id, request_index,
prompt_tokens, cached_tokens, uncached_tokens, output_tokens,
ttft_ms, request_duration_ms, finish_reason,
tool_name, tool_result_size
```

WIDI profile 的 `tools` frontmatter 在启动时声明可用工具；`context.actions.setTools()` 与 `setActiveTools()` 会运行中改变工具集。E06 必须使用前者，后者会改变后续请求的 tool schema，破坏可比性。

## 6. 工具集：最小、固定、离线

历史 P4A 的 tools 段约占首请求 83% token，并且 MCP 启动曾造成多种 tools schema。E06 不接入远程 MCP，也不试图复刻该不稳定条件。

首轮所有 arm 启用相同工具集：

```text
read
grep
find
write
p4a_apply_judgment
p4a_validate_outputs
[p4a_lookup_evidence]               # 仅当冻结 evidence bundle 确有需要
```

默认禁用：

```text
bash
edit
ls
spawn_agent
send_message
watch_agent
GitHub / HuggingFace / arXiv MCP
```

冻结的 evidence bundle 保留原 P4A 检索获得的信息；离线化是控制 network、schema 与内容漂移，不是删除任务证据。输出契约仅允许生成 `agent_judgment.json`，再经固定工具 merge 与 validate。

## 7. P4A case 选样与 fixture qualification

历史 session 不能直接 rerun：旧 workspace、网络状态、外部结果和最终产物可能已不可获得。每个入选 session 先完成 fixture qualification。

### 样本池

从 E01 的 `s0_manifest.jsonl` 和 `s2_session_stats.jsonl` 中筛选：

- `family = extract`；
- 单轮用户输入；
- 正常 `end_turn`；
- 非 aborted、非 operator chat；
- 可恢复任务输入与可审计质量目标；
- 同属 `paper-mineru-resource-extract` task family。

repair 不与 extract 混入本轮：两者输入形态、工具行为与 quality metric 不可直接合并。

### 数量与分层

准备 24 个 case：4 个 development/smoke case 与 20 个冻结 evaluation case。20 个正式 case 按历史轨迹复杂度分层，每层 5 个：

1. 低步骤、少外部检索；
2. 中位步骤；
3. 长轨迹；
4. 高资源歧义或高 validation/repair 压力。

每个 case 采用固定目录：

```text
fixtures/<case-id>/
├── task.json                         # paper_id、原任务、来源 session id、轨迹摘要
├── input/
│   ├── paper.md
│   ├── input_bundle.json
│   ├── references.jsonl
│   ├── citation_contexts.jsonl
│   └── evidence/
├── expected/
│   ├── schema.json
│   └── adjudication.json
└── output/                            # 每次 run 使用独立副本
```

旧 agent 的输出不能未经审查直接作为 gold。质量至少包括既有 P4A validator 的 schema/consistency pass，以及对 resource precision、recall 和关键字段的盲审或独立 adjudication。任何无法恢复输入或质量目标的典型 session 都应剔除。

## 8. 运行协议

### 固定条件

- 固定 `packages/widi` gitlink、模型 checkpoint、tokenizer/chat template、temperature、最大上下文与 provider 参数。
- 固定 vLLM `0.22.1` 并启用 `--enable-prompt-tokens-details`。
- 固定工具 schema 及其顺序；串行运行 agent，不并发发送模型请求。
- 每个 arm 使用相同 case 与相同 case 顺序。
- 每个 batch 从空 cache 开始：重启 server 或通过已验证方法清空 KV cache；前一 arm 的残留不得惠及下一 arm。

### 重复与顺序

正式设计为：

$$
20\ \text{cases} \times 3\ \text{arms} \times 3\ \text{independent batches}
= 180\ \text{runs}.
$$

每个 batch 内 case 顺序一致；batch 间轮换 arm 顺序。先用 4 个 development case 验证 telemetry 与 validator，再冻结 manifest 并运行 20-case evaluation。

## 9. 指标与报告

逐请求定义：

$$
\text{uncached input} = \text{prompt tokens} - \text{cached tokens}.
$$

每个 arm 报告：

- $\sum \text{cached tokens}$ 与 $\sum \text{uncached input tokens}$；
- 首请求、后续请求、batch 首 case 与 batch 中第 2–20 case 的分组结果；
- TTFT、总 wall time、输出 token 与 decode 成本；
- KV cache 占用、preemption、eviction；
- validator pass、盲审质量、repair 次数、工具调用数。

A2 可能降低 uncached prefill，但也可能因更长 stable prefix 增加 KV 占用；报告必须同时包含命中/未命中 prefill、KV、decode 与任务质量。历史 P4A 的零 cache 字段不可用于这些指标。

## 10. 实施与验收顺序

1. 固定 `packages/widi` gitlink 与 A0/A1/A2 agent-dir 命名。
2. 从 3999 个 E01 纳入 session 中筛出候选，完成 24 个 fixture 的 qualification。
3. 实现共同的 layout、fixture-tools、telemetry extension，并使三臂共用同一 schema。
4. 在 4 个 development case 上验收：
   - 三臂 tool schema hash 相同；
   - 除 layout digest 外，其余 manifest digest 相同；
   - vLLM usage 返回非伪造的 `cached_tokens`，且与 server metrics 一致；
   - 每个 run 可生成并验证输出；
   - A1/A2 的 token-level prompt 顺序符合定义。
5. 冻结 fixture 与 manifest，执行三 batch、20-case evaluation。
6. 仅在 A2 成为可信强 baseline 后，再设计并实现 A3。
