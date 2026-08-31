# p4a 与 CachePlan 的关系

## 1. p4a 是什么

p4a（`experiments/p4a/`）是一个**历史项目**：使用 kimi-code CLI，按统一的 skill/agent_prompt 流程，对 ACL 2025 主会全部论文做批量抽取——识别论文中提到的 codebase、benchmark、dataset 等资源，并抽取论文阅读相关的结构化信息（`paper_record` / `resource_records` 等）。流程细节见 `experiments/p4a/refractor.md`。

p4a 本身**不是** CachePlan 要验证的研究方法，而是一个已经完成、独立运行过的应用项目。

## 2. 与 CachePlan 研究方向的关系

CachePlan 的核心研究问题见 [AGENTS.md](../AGENTS.md)：能否在不明显牺牲 agent 能力的前提下，设计 agent 的规划/执行方式以提升 prompt-cache 复用率。

p4a 是这个研究问题的**动机来源**，而非研究本身：

- 运行 p4a 时观测到的现象——ReAct 循环每步重发全部历史，导致单篇论文累计计费 input 是最终真实上下文的 10–18 倍——直接启发了 CachePlan 的立项。
- 保留下来的 kimi-code session 日志（`data/raw/kimi-p4a-sessions.tar.gz`）是一批真实、大规模、非人工构造的 agent 执行轨迹，可以作为研究中的**样本/案例实验**，但不是**主实验**。主实验负责受控地验证 CachePlan 方法本身是否有效；p4a 数据负责提供真实世界的问题规模刻画和轨迹特征分析，两者结论不能互相替代。

已知的复现结果（2026-08-31，随机抽样一条 session，编号 `session_0b334391-...`，对应论文 `2025.acl-long.114`）：

- 19 轮对话，累计计费 input 1,893,916 token，最终真实上下文 121,499 token，放大倍数 15.6x，与 `refractor.md` 里给出的整体统计一致。
- 该 session 全部 19 条 `usage.record` 的 `inputCacheRead` / `inputCacheCreation` 均为 0——尚未确认是全量数据的普遍现象还是这条样本的个例，见第 4 节的先决核查项。

## 3. 数据资产说明

- 压缩包：`data/raw/kimi-p4a-sessions.tar.gz`（已 gitignore，不进版本库）。
- 解压后结构：`data/raw/kimi-p4a-sessions/.kimi-code/sessions/<workdir_id>/session_<uuid>/`，每个 session 目录包含：
  - `state.json`：任务的原始 prompt（`lastPrompt`）、创建/更新时间。
  - `logs/kimi-code.log`：每个 turnStep 的模型配置（model、thinkingEffort、systemPromptChars、toolCount）与请求时间戳。
  - `agents/main/wire.jsonl`：完整 wire 协议轨迹，包含 `usage.record`（逐 turn 的 input/output/cache 字段）、`context.append_message`（用户消息与 system-reminder 注入）、`context.append_loop_event`（`tool.call` / `tool.result` / `step.begin` / `step.end` / `content.part`，即逐步的工具调用序列与助手输出）。
- 共约 12,801 个文件，对应全量 ACL 2025 主会论文的批量运行记录。

## 4. 应用与推进规范

1. **只读、不可变**：p4a 的历史数据（session 日志、`experiments/p4a/` 下已有代码）是既成事实，不应为了"配合新研究"而修改或重跑。需要新的分析逻辑，写在分析脚本里，不要改动原始日志或 p4a 自身流水线代码。
2. **代码隔离**：`experiments/p4a/` 保持独立、少改动，不与 CachePlan 核心方法代码耦合。只有确认被多个实验复用的部分（轨迹解析、cache 命中率计算等），才下沉为共享分析工具，且放在 CachePlan 自己的代码路径下，不塞进 `experiments/p4a/` 内部。
3. **先决核查项（未做之前不得下结论）**：批量核实全部 12,801 个 session 的 `inputCacheRead` / `inputCacheCreation` 是否恒为 0。
   - 若非恒零：可以计算真实 cache 命中率分布，作为强证据使用。
   - 若恒为零：说明该字段在这套 openai 兼容 provider 下未被正确采集，只能退回基于 prompt 前缀 token 重叠度的**代理指标**，报告中必须明确标注这是估算值而非真实命中率。
4. **用途边界**：p4a 数据只能用于**诊断性/动机性分析**——问题规模刻画（token 放大倍数分布）、轨迹方差分析（语义等价但表达不同导致的前缀差异）、system-reminder 等注入内容对轨迹的影响。**不能**直接作为"CachePlan 方法是否有效"的对照组基线：p4a 使用的模型（Kimi CLI + qwen3.6-35b-a3b）和 serving 环境与主实验大概率不同，且离线日志无法反事实重放一个改变了 agent 行为的新策略。方法有效性的验证仍需在同一套 infra 上重新跑受控对比。
5. **派生产物存放**：任何从 session 日志聚合出的表/图（如 `session_id, paper_id, n_turns, cumulative_input, final_input, cache_read_sum, wall_time` 汇总表）写入 `data/processed/`（已 gitignore），并在文件或伴随说明中标注数据来源（源自哪个 tar.gz 版本、生成脚本、生成日期），保证可追溯。
6. **泛化边界**：p4a 是"批量 agent 处理数据"这一类研究实践的一个实例，其轨迹结构（长 ReAct 循环、固定 skill 模板、MinerU/vLLM 特有的工具集）比较特定。样本实验部分若要支撑更普遍的结论，应在后续补充至少一个结构不同的批量 agent 工作负载，不能只靠 p4a 一个案例撑起"批量 agent 场景"的泛化论断。
7. **引用规范**：在报告/论文中提及 p4a 数据时，明确标注为"案例研究"或"动机性观测"，与主实验的受控结论分节陈述，避免使用暗示因果验证的措辞（如"证明了""因此方法有效"）。
