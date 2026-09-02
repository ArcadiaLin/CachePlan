# Open Question: Where Should Reusable Context Live?

> **一句话**：如果每个 run 都必然要加载同一份 Skill，为什么不直接把它写进 system prompt？
> 这不是一个实现细节问题——**"把可复用指令塞进 system prompt" 是本项目必须先打败的第一个 baseline**，
> 而它能吃掉多少收益，决定了 cache-aware planning 还剩多少研究空间。

提出日期：2026-09-02。状态见 [`PROGRESS.md` → Open Questions](../PROGRESS.md#open-questions)。

## 1. 问题

从 prefix cache 的角度，静态注入是很漂亮的：

```
run i:   [system prompt + Skill 内容] + [User: Task A]
run i+1: [system prompt + Skill 内容] + [User: Task B]
          └────── 逐 token 相同，天然是稳定可缓存前缀 ──────┘
```

相比之下，P4A 现在的做法是：

```
User: 处理论文 A
Assistant: 我先读 prompt 文件
Tool:  Read(/<paper_id>/agent_prompt.md)
Assistant: 我来加载 skill
Tool:  Read(skill/.../SKILL.md)
Assistant: ...
```

后者多一次（这里是两次）agent step 和 tool call，并且把"读完 skill 之后形成的轨迹"变得不稳定。
审稿人一定会问 **"Why don't you simply put the reusable instructions into the system prompt?"**，
这个问题必须用实验回答，不能用论述回答。

## 2. P4A 现状核实（事实）

以下是从语料里核实过的，不是推测：

| 事实 | 证据 |
|---|---|
| 初始 user prompt 仅 359 字符（≈109 token） | 任一 session 的 `state.json.lastPrompt`；与 [E01](../experiments/e01-p4a-trajectory.md) §3.1 渲染出的 "user 段 109 tok" 一致 |
| Skill 是**两跳**进上下文：先 Read 每篇论文各自的 `agent_prompt.md`，再由它指名 skill | 同上 prompt 原文 |
| 第一个工具调用 100% 是 Read，但**参数含论文 id** | E01 §2 s2 附带 |
| 已经不是单 skill：`experiments/p4a/skill/` 下有 2 个变体（mineru 21,014 字符 ≈5.3k token；latex 8,964 字符 ≈2.2k token），按论文来源选 | 仓库文件 |
| 跨 run 公共前缀在 ≈24.5k token 处断裂（tools 段 22,575 + systemPrompt 可复用部分 ≈1,952） | E01 §3.2 |

第 3 条是关键：**第一个 assistant 动作里就嵌了论文 id**，所以跨 run 的共享前缀到此为止。
Skill 内容——3999 个 run 里逐字相同的那 5.3k token——落在分叉点**之后**，跨 run 大概率一次都没被复用过。
这个 baseline 要做的事，本质上是把一块已知恒定的内容从分叉点之后搬到分叉点之前。

## 3. 四种策略与 trade-off

| 策略 | Cache locality | 输入冗余 | 灵活性 |
|---|---|---|---|
| S1 All skills in system prompt | 极高 | 高 | 低 |
| S2 Task-specific skill injection（编排层选好后拼进 system） | 中/高 | 低 | 中 |
| S3 Agent dynamic skill loading（P4A 现状） | 低/不稳定 | 最低 | 高 |
| S4 Cache-aware planning | 目标：高 | 目标：低 | 高 |

S1 的代价在 skill 数量上放大。设 $N$ 个 skill、平均 $s$ token，单次任务实需 1 个，则 S1 每个 run 多带 $(N-1)\cdot s$ token 的无关上下文。
$N=2$（P4A 今天）几乎无感；$N=30$ 就是把绝大部分 token 花在与当前任务无关的指令上。
S2 输入短，但每个 skill 组合是一条独立前缀，共享前缀被切碎。
**S4 这一行才是本项目声称的研究空间**——问题因此从"怎么让 agent 读 skill 时更 cache-friendly"升级为：

> Agent 应该如何组织和规划 reusable context / execution trajectory，
> 使 inference cache reuse 最大化，同时避免无关上下文带来的额外计算？

## 4. 两个陷阱（写在前面，因为它们会让实验结论失真）

### 4.1 天真实现的 S1 可能得零分

"把 skill 追加到 system prompt 末尾"在 kimi-code 的布局下**几乎没有收益**：
模板把 tools 放在首条 system message 最前，其后是 `systemPrompt`，而 `systemPrompt` 里含毫秒级 ISO 时间戳和工作目录树（E01 §3.2，300 份采样的跨 run 公共前缀中位数只有 1952/3270 token）。
追加在其后的 skill 位于易变块**之后**，前缀早已断裂，缓存不到。

所以 S1 的正确强形式是 **static-first layout**：`tools → skill → 易变块 → user`，或把易变块整体后移到首条 user 消息。
这条必须写进实验设计，否则会得到一个"system prompt baseline 没用"的假阴性结论。

同理，MCP 工具集变体（E01 §3.3，全语料 4 个 `toolsHash`）位于 prompt 最前，github MCP 启动超时会让前缀从 token 0 断裂——它在所有这些布局之前，必须先固化。

### 4.2 只看 prefill token 会让 S1 白嫖

如果指标只有"cache hit rate"或"未命中 prefill token 数"，S1 是**无条件最优**的：塞进前缀的东西一律命中，指标上等于免费。
但它不免费：

- **KV 显存**：命中的前缀照样要占 KV cache，直接压低并发批量；
- **decode 成本**：每生成一个 token 的 attention 代价随上下文长度增长，这部分完全不受 prefix cache 影响；
- **任务质量**：29 个无关 skill 稀释注意力，这是 context pollution 的实际后果，不是修辞。

**代价模型必须同时含这四项**（命中/未命中 prefill 分别计价、KV 占用、decode 侧成本、任务质量），否则整个 trade-off 表塌缩成"全塞 system prompt"。

## 5. 这个 baseline 在 P4A 上的上界（可算的部分）

区分两种记账口径：

- **现状口径**（会话内缓存未生效/未上报）：单 run 累计 prefill p50 = 1,285,334 token，放大 12.0×（E01 §2 s2）。
- **理想口径**（会话内前缀缓存完美）：单 run prefill = 峰值上下文 p50 ≈ 106,416 token。

**跨 run 复用只在理想口径下有意义**——会话内的 12× 重复是另一个问题，且已被现成的 prefix caching 解决。在理想口径下：

| 分段 | 规模 | 跨 run 可复用？ |
|---|---:|---|
| tools + 可复用 systemPrompt | ≈24.5k | 是（现状已复用） |
| Skill 内容 | ≈5.3k（mineru）/ 2.2k（latex） | **否（现状），S1 后变为是** |
| 论文正文 | 待 s3 测 | **永远否**——每个输入私有 |
| 轨迹（assistant 输出 + 工具结果） | 待 s3 测 | 本项目方法的战场 |

即 S1 大致把跨 run 可复用比例从 $24.5/106 \approx 23\%$ 抬到 $\approx 28\%$。这是**乐观上界**，因为它假定 static-first layout 已做、工具集已固化。

关键推论：**任何方法的跨 run 复用上限都被"论文正文"这一段封死**。
所以 s3 必须给出三分解——静态前缀 / 每输入私有内容 / 生成轨迹——这三个数出来之前，无法判断 S4 相对 S1 还剩多少空间。这是本 OQ 对 E01 提出的具体要求。

## 6. 实验设计

四个臂，同一 infra、同一模型、同一批输入：

| 臂 | 内容 |
|---|---|
| A0 | P4A 现状（S3：两跳动态加载） |
| A1 | Skill 直接拼进 system prompt，**其余布局不动**（天真 S1，用于验证 §4.1 的陷阱确实存在） |
| A2 | Static-first layout：工具集固化 + `tools → skill → 易变块`（S1 的强形式，**这才是要打败的 baseline**） |
| A3 | 本项目方法叠加在 A2 之上 |

**判据：本项目的贡献必须报告为 $A3 - A2$，不是 $A3 - A0$。** 拿 A0 当对照会把静态布局的收益算进方法的账上。

指标（每臂都要全量，缺一不可）：

- 逐请求 `cached_tokens`（vLLM 0.22.1 + `--enable-prompt-tokens-details`，E01 §2 s1 已验证可用）；
- 未命中 prefill / 命中 prefill / decode token，三者分开计价；
- 峰值上下文与 KV 占用；
- 端到端延迟与 wall time；
- **任务质量**：抽取 precision/recall、validation 通过率、repair 触发率。A1/A2 改变了 skill 在上下文中的位置和角色（tool result → system message），这本身可能改变指令遵循程度，质量不测则整个对比不可解释。

多 skill 场景（$N \gg 2$）P4A 给不出来，需要单独构造：在同一套 workload 上人为扩充 skill 库，扫 $N$，观察 S1 与 S2 的交叉点在哪。这是把结论从"P4A 这一个实例"推广到"这类 workload"的必要条件，也呼应 [`p4a.md`](../experiments/p4a.md) 第 4 节第 6 条的泛化边界。

## 7. 可能的结局

- **S1/A2 吃掉绝大部分收益**：那就如实报告——对单 skill、固定流程的 workload，正确答案是静态布局，不是 planning。研究要么转向 $N$ 大的多 skill 场景（那里 S1 的 context pollution 代价才显现），要么承认这类 workload 不需要本方法。
- **A2 明显不够**：说明收益的大头在轨迹段而非前缀段，motivation 成立，且此时已经有一个诚实的强 baseline 垫底，$A3 - A2$ 就是干净的贡献。

无论哪种，先测 A2 都是正确的下一步。**如果一个简单的 system-prompt baseline 就能解决 90% 的问题，就不该硬造复杂方法。**

## 8. 关系

- 依赖 [E01](../experiments/e01-p4a-trajectory.md) s3 的三分解（§5）与 s4 的分歧归因；s3 未验收前无法给这个问题定价。
- 与 [OQ1（agentic execution 的必要性）](Necessity-of-agentic-execution.md) 正交但同源：OQ1 问"要多少 agency"，本问题问"可复用上下文该放在哪"。两者都是在检查一个更简单的方案是否已经够用——OQ1 的更简单方案是 workflow，本问题的是静态前缀。
- 对 E02 的约束继承 E01 §6，并追加：工具集必须固化（否则 §4.1 的从 token 0 断裂会淹没所有布局差异）。
