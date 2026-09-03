# E06 — Execution-level prefix reuse：P4A-derived WIDI 重执行

**状态：重新设计中。** E06 是 CachePlan 的第一个受控实验，不重放历史 P4A/Kimi 运行。它在固定 WIDI runtime、模型服务、工具 schema 和冻结输入上，比较三种可复用 context strategy。此前只比较 skill 在 prompt 中位置的 static-prefix 设计保留为后续 baseline，不属于当前 E06。

**前置闸门：** E01 s3 的精确 prompt 复现及其三段 token 分解必须验收。E01 的历史 cache 字段恒为 0，是旧 provider 上报缺陷；E06 必须通过 vLLM 0.22.1 的 `cached_tokens` 直接取得真实逐请求命中数据。见 [`e01-p4a-trajectory.md`](e01-p4a-trajectory.md) §2–4。

## 1. 研究问题与边界

E06 回答 OQ2 的当前问题：

> 对于重复执行的同类 agent task，能否复用 execution-level prefix，而不只复用 skill 文本，从而减少重复 prefill 并获得跨 run 的 prefix-cache 收益？

设 $B$ 为不含 case 内容的 skill-understanding trajectory，$T_i$ 为 case $i$ 的任务。E06 比较动态加载、静态知识注入，以及在 $B$ 后追加 $T_i$：

$$
\text{tools} \rightarrow \text{system} \rightarrow B \rightarrow T_i.
$$

P4A 的用途受以下边界约束：

- 历史 P4A 日志和既有工程保持只读、不可变。
- 选取的 P4A case 会被 fixture 化后由 WIDI 重新执行；历史 token/cost 不作为本实验对照数据。
- 第一轮只覆盖 P4A Layer-4 resource judgment / validation slice，而不是完整外部网络检索流水线。
- A2 的 shared prefix 不含 case 数据、输出或跨 case mutable state；它只包含固定 bootstrap prompt、skill read tool call/result 与 bootstrap completion。
- 结论应表述为 P4A-derived workload 上的受控结果，不外推为所有 agent workload。

详见 [`p4a.md`](p4a.md) §2–4。

## 2. 固定 WIDI runtime，隔离 WIDI 配置变体

`packages/widi/` 是本项目唯一的 WIDI runtime submodule。它是可演化的个人项目：需要新的 runtime 行为时，在 WIDI 仓库中提交该变更，再由父仓库更新 `packages/widi` 的 gitlink。每次实验运行都必须记录该 gitlink revision；同一 E06 对比中的所有 arm 必须使用完全相同的 revision。

目标配置变体由 `launch.sh` 选择：

```text
packages/
└── widi/                                   # 固定 gitlink 的 WIDI runtime

widis/
├── .widi-e06-a0-dynamic/
├── .widi-e06-a1-naive/                     # A1 static-knowledge arm
└── .widi-e06-a2-static-first/              # A2 execution-prefix arm
```

后两个目录保留历史文件名，但不再表达实验语义；`launch.sh` 将显式 arm 参数传给 controller，并要求它与 run plan 的 `arm` 一致。它们不是可互换别名，也不会通过 profile、工具或默认 agent-dir 隐式选择。
任何 WIDI runtime 修改都是另一条消融轴；比较两个 revision 时，对每个 revision 分别完整运行 A0/A1/A2，并以 gitlink revision 区分结果。不得在单次 A0/A1/A2 对比中混用 WIDI revision。

## 3. 处理臂

三臂共享 provider、模型、WIDI revision、tokenizer/chat template、工具 schema、fixture、case 顺序和单 agent protocol。A0 与 A2 使用字节完全相同的 generic system prompt；A1 仅在其后追加对 canonical Skill 的冻结摘要。

| Arm | Agent dir | 可复用 context strategy | 首次 case 前的协议 |
| --- | --- | --- | --- |
| A0 | `.widi-e06-a0-dynamic` | 无 execution reuse；每 case 动态读 skill | controller 创建 fresh agent；agent 读取 skill 后执行 case |
| A1 | `.widi-e06-a1-naive` | static knowledge reuse | controller 创建 fresh agent；generic system prompt 追加 skill 摘要后执行 case |
| A2 | `.widi-e06-a2-static-first` | execution-level prefix reuse | 一个 agent 完成稳定 bootstrap；每 case 从该 prefix 追加相同 task |

### A0 — Dynamic loading

```text
tools
→ generic system prompt
→ user: case task + “read and understand the skill instructions”
→ agent: read skill and execute case
```

每个 case 都由 fresh agent 重新读取并理解 canonical Skill。controller 对每 case 切换独立的 fixture 副本；除更早的通用 tools/system 前缀外，不复用此前 case 的 execution context。

### A1 — Static knowledge reuse

```text
tools
→ generic system prompt + frozen Skill summary
→ user: case task
```

A1 不执行 bootstrap trajectory。`static-knowledge.md` 是 canonical Skill 的冻结操作摘要，作为静态 section 追加到 system prompt。它表示常见数据处理工作流中“将 procedure 总结为 system prompt”的处理臂，不与 A0/A2 的 generic system prompt 混淆。

### A2 — Execution-level prefix reuse

```text
tools
→ generic system prompt
→ user: fixed bootstrap request to understand the working guideline
→ assistant: read("procedure/SKILL.md")
→ tool result: canonical skill body
→ assistant: bootstrap completion
→ user: case task
```

每个 batch 只构造一次稳定 bootstrap trajectory $B$，并保存其 leaf id 与可审计 transcript。每个 case 都从该 leaf 发起 case prompt，结束后导航回同一 leaf；case branch 不保留为下一 case 的上下文，因此不共享输出、工具状态或 case context。

首个 skill read 必须使用现有 `read` 工具和固定相对路径 `procedure/SKILL.md`。禁止 skill listing、`find`、新建 skill-read 工具或 controller 代替 agent 执行读取：它们会改变 schema 或 bootstrap trajectory。A2 的验收对象是每个 case 首请求在 tokenizer/chat-template 层包含与 $B$ 完全相同的前缀，并由 vLLM 报告该前缀的 cache 命中。

## 4. Agent-dir 与配置不变量

每个 arm 的 agent dir 保持相同骨架：

```text
widis/.widi-e06-a*/
├── settings.json
└── profiles/
    └── p4a-e06.md
```

共同不变量：

- canonical Skill、A1 `static-knowledge.md`、A2 bootstrap request、run plan 和 fixture manifest 都是实验输入；run manifest 记录实际路径、运行时 gitlink、profile、extension、tool schema 与 case 顺序。
- 三臂 profile body 必须字节相同。A0/A2 generic system prompt 必须字节相同；仅 A1 的 controller Core half 追加 static-knowledge section。
- profile 默认设置 `projectContext: false`、`includeCwd: false`、`skillsListing: false`。任何例外必须成为显式实验变量；工作目录、项目 context 或自动 skill listing 不得暗中进入 system prompt。
- A0/A1 的 fresh case agent 与 A2 的 bootstrap agent 均不允许 delegation；controller 本身不向模型暴露工具。A2 每个 case prompt 完成后使用公开 `navigateTree(bootstrapLeafId)` 回到同一 leaf。
- 所有正式启动都经 `launch.sh <arm> <run-plan.json>`，显式传入 `--agent-dir`、`--cwd`、两份共同 extension、`--mode print` 和 `--emit`；不得回退到 WIDI runtime submodule 内的 `.widi/` 或 TUI。

## 5. 共同 extension 与执行控制器

所有臂加载相同 extension 集与相同版本；arm-specific 行为仅由 `launch.sh` 传入的 `E06_ARM` 与 run plan 的同名字段选择，不能通过增减 model-visible tool 实现。

### `e06-execution-prefix`

这是纯 Core extension；它由 WIDI print mode 在 root agent 创建后接收 `e06-execution-prefix:run` 事件。`contracts/run_plan.json` 指定 arm、case 顺序、fixture root、canonical Skill 和本次 run root。`launch.sh` 为该 run 提前创建固定的 `run_root/active` cwd。

- 每次 case 前，controller 将对应 fixture 的只读 `input/` 复制到 `active/input/`，创建空的 `active/output/`，并将 canonical Skill 复制为 `active/procedure/SKILL.md`。case 完成后，它将 `active/output/` 归档到 `run_root/cases/<case-id>/output/`；原 fixture 永不写入。
- A0：controller 创建 fresh agent，发送要求先读取 `procedure/SKILL.md` 的 task。
- A1：controller 创建 fresh agent；该 agent 的 Core half 已将 `static-knowledge.md` 追加到 generic system prompt，再发送 case task。
- A2：root agent 先收到固定 bootstrap task，并自行 `read("procedure/SKILL.md")`；controller 记录 bootstrap leaf id。它在每次相同的 case task 前切换 active fixture，case 结束后归档 output 并 `navigateTree(bootstrapLeafId)`。

controller 不注册业务工具，不写 `context.session.appendEntry()`，不把 cursor、leaf id 或 case result 放进模型上下文。它将 lifecycle、prompt outcome、A2 leaf 回退和失败写入 session 外的 `run-manifest.jsonl`，并以 extension event 让 print-mode stdout 输出可消费的完成或失败事件。A2 的实际 cache hit 仍须在 smoke 验收中由 telemetry 与 vLLM 证明；controller 存在本身不是该证明。

`launch.sh` 同时将 print-mode JSONL 镜像到 `run_root/print.jsonl`；若 controller 发出 `e06-execution-prefix:failed`，wrapper 即以非零状态退出，即使 WIDI host 仅将 extension handler 异常报告为 diagnostic。


### `e06-fixture-tools`

将 P4A judgment 阶段需要的本地操作封装成固定、可审计且输出有界的工具：

- `p4a_apply_judgment`：校验并规范化当前 case 的 `agent_judgment.json`。
- `p4a_validate_outputs`：运行固定 schema/consistency validator，返回结构化结果。

它们替代通用 shell 命令，避免命令措辞、任意外部访问和无关工具轨迹成为变量。路径策略允许 bootstrap 阶段只读 `procedure/SKILL.md`；case 阶段只读 `input/`、只写 `output/agent_judgment.json`。

### `e06-telemetry`

只观测，不干预。通过 `agent_harness_event` 或 provider trace 写入 session 外的 append-only JSONL；不得调用 `context.session.appendEntry()`。

每个请求至少记录：

```text
run_id, batch_id, arm, case_id, request_index, phase,
prompt_tokens, cached_tokens, uncached_tokens, output_tokens,
ttft_ms, request_duration_ms, finish_reason,
tool_name, tool_result_size, prefix_template_version
```

WIDI profile 的 `tools` frontmatter 在启动时声明可用工具；运行中不得调用 `context.actions.setTools()` 或 `setActiveTools()`，否则后续请求的 tool schema 会漂移。

## 6. 工具集：最小、固定、离线

历史 P4A 的 tools 段约占首请求 83% token，并且 MCP 启动曾造成多种 tools schema。E06 不接入远程 MCP，也不试图复刻该不稳定条件。

所有 arm、所有 phase 启用相同 model-visible 工具集：

```text
read
grep
find
write
p4a_apply_judgment
p4a_validate_outputs
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

冻结 evidence bundle 保留原 P4A 检索获得的信息；离线化是控制 network、schema 与内容漂移，不是删除任务证据。输出契约仅允许生成 `agent_judgment.json`，再经固定工具 apply 与 validate。

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

源 fixture 是只读输入：

```text
data/processed/e06/
├── fixtures/<case-id>/
│   ├── case.json                       # paper_id、来源 session 与轨迹摘要
│   └── input/                          # paper、contract、references、contexts、evidence
└── expected/<case-id>.json             # 历史恢复比较基线；不对 agent 可读
```

每次 run 的 controller 物化自己的 active workspace：

```text
<run-root>/
├── active/
│   ├── procedure/SKILL.md              # canonical Skill 的本次副本
│   ├── input/                          # 当前 case 的独立副本
│   └── output/                         # 当前 case 的空输出目录
├── cases/<case-id>/output/             # case 完成后归档
└── run-manifest.jsonl
```

controller 在 case 间清除并重建 `active/input/` 与 `active/output/`；A2 只保留 session 的 bootstrap leaf，绝不保留上一 case 的文件内容、模型 context 或输出。

旧 agent 的输出不能未经审查直接作为 gold。质量至少包括既有 P4A validator 的 schema/consistency pass，以及对 resource precision、recall 和关键字段的盲审或独立 adjudication。任何无法恢复输入或质量目标的典型 session 都应剔除。

## 8. 运行协议

### 固定条件

- 固定 `packages/widi` gitlink、模型 checkpoint、tokenizer/chat template、temperature、最大上下文与 provider 参数。
- 固定 vLLM `0.22.1` 并启用 `--enable-prompt-tokens-details`。
- 固定工具 schema、工具顺序和 controller version；串行运行 agent，不并发发送模型请求。
- 每个 arm 使用相同 case 与相同 case 顺序。
- 每个 arm 的每个 batch 从空 cache 开始；前一 arm 的残留不得惠及下一 arm。

### A2 bootstrap 与重复

每个 A2 batch 清空 cache 后，先执行一次 bootstrap $B$，再顺序运行该 batch 的 cases。$B$ 的模型请求、tool call 和完成均计入该 batch 的总成本；它不能被当作免费 warm-up。每个 A2 case 都从同一 bootstrap leaf 发起，结束后回退，因此 case 间只共享服务端 KV cache，不共享 case state。

正式 evaluation 为：

$$
20\ \text{cases} \times 3\ \text{arms} \times 3\ \text{independent batches}
= 180\ \text{case runs},
$$

外加 A2 每 batch 一次、共 3 次 bootstrap。每个 batch 间轮换 arm 顺序。先用 4 个 development case 验收 telemetry、prefix equality 与 validator，再冻结 manifest 并运行 20-case evaluation。

## 9. 指标与报告

逐请求定义：

$$
\text{uncached input} = \text{prompt tokens} - \text{cached tokens}.
$$

对 A2，bootstrap 计入 amortized 总量：

$$
P_{\mathrm{A2}} =
P_B + \sum_i P_{T_i},
\qquad
\bar P_{\mathrm{A2}} = \frac{P_B + \sum_i P_{T_i}}{N}.
$$

其中 $P$ 可分别替换为 raw input tokens、uncached prefill tokens、inference cost 或 latency。必须同时报告 bootstrap-inclusive 与 case-only 指标；A2 可能拥有更多 raw input tokens，却以较少 uncached prefill 获益。

每个 arm 报告：

- total input tokens、cached prefix tokens、uncached prefill tokens；
- bootstrap-inclusive 与 case-only total inference cost、TTFT、request latency 和 total wall time；
- batch 首 case、batch 中后续 case、A2 bootstrap 与 A2 branch 首请求的分组结果；
- KV cache 占用、preemption、eviction；
- validator pass、盲审质量、repair 次数、工具调用数。

核心假设是：在任务质量不劣的前提下，A2 execution-level reuse 的 amortized uncached prefill、成本和延迟优于 A1 static knowledge reuse，后者优于 A0 dynamic loading。结果不得只以 cache hit ratio 判定；A2 是否抵消 bootstrap 的额外成本必须由上述总量验证。

## 10. 实施与验收顺序

1. 固定 canonical Skill、`static-knowledge.md`、A2 bootstrap request、run plan 与 active-workspace layout；不实现旧的 skill-placement-only `e06-layout` experiment。
2. 经 `launch.sh <arm> <run-plan.json>` 启动 print mode。controller 必须只接受 arm 一致的 plan，创建 `run_root/active`，将每个 case 的 input/output 与归档彼此隔离，并写入 session 外的 run manifest。
3. 以一个 smoke case 最小复现公开 `getLeafId()` / `prompt()` / `navigateTree()` 路径：A2 必须完成 bootstrap，记录 leaf，并在 case 后成功回退；每次 cache reset 后重新 bootstrap。
4. 实现 telemetry extension，使三臂 model-visible tool schema 相同，并将 provider 的 cache/token/latency 事实关联到 controller 的 run manifest。
5. 在 4 个 development case 上验收：
   - 三臂有效 tool schema 与顺序相同；
   - A0/A2 generic system prompt 相同；A1 仅多出 `static-knowledge.md`；
   - 每个 A2 case prompt 前都导航回同一 bootstrap leaf，且 bootstrap transcript 与共享 prefix token 序列相同；
   - vLLM `cached_tokens` 与 server metrics 一致，且 A2 case 请求实际命中 bootstrap prefix；
   - 每个 run 可生成并验证输出，且 historical expected 不进入 agent 可读路径。
6. 冻结 fixture、run plan 与 controller version，执行三 batch、20-case evaluation；报告 bootstrap-inclusive 成本。
