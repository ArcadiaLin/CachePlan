# E06 serial-r1-retry 批次粗略报告(2026-09-03)

> **粗略报告,未与任何正式实验记录对齐。** 数据来源:`runs/e06-serial-r1-retry/{a0,a1}` 与 `runs/e06-a2-shared-root` 的 `print.jsonl` / `run-manifest.jsonl` / `session-metrics.json`。分析脚本为一次性的 `tmps/e06-r1retry-summary.py`。

## 批次构成

- 3 个 arm × 4 个 case(eval-low-01~04),模型 `vllm/qwen3.6-35b-a3b`,fixture 来自 `data/processed/e06/fixtures`。
- a0(dynamic):每 case 新 agent,prompt 里显式要求先读 SKILL;a1(naive):每 case 新 agent,static-knowledge 进 system prompt;a2(static-first / shared-root):单 session,bootstrap 读 SKILL 后每 case 回卷到 bootstrap leaf。
- 运行时刻:a0 09:47 起,a1 在其后,a2 批 09:56:32 起(UTC),串行。

## 完成情况(形式上全部完成)

- 12/12 case `case_completed`,每个 run `status: ok`、exit 0,`p4a_validate_outputs` 最终全过,provider 0 错误,0 compaction。
- 每 case 耗时:a0 = 57/63/92/42s,a1 = 62/45/90/67s,a2 = 116/62/100/75s。
- 工具失败(均被 agent 重试纠正):a0 41 次(find 14 全败、read 11、apply 8、grep 7、write 1),a1 9 次(apply 5、read 4),a2 12 次(apply 6、read 6)。

## Cache 与成本

口径:reuse = `cacheRead / (uncached input + cacheRead)`;`cacheWrite` 全为 0(vLLM APC 透明)。成本折算:uncached=1,cached=0.1,output=1。

| arm | uncached | cacheRead | output | reuse | 折算成本 | 无缓存基线 | 节省 |
|---|---|---|---|---|---|---|---|
| a0 | 178,714 | 1,881,792 | 37,345 | 0.9133 | 404,238 | 2,097,851 | 80.7% |
| a1 | 163,958 | 1,687,488 | 39,529 | 0.9114 | 372,236 | 1,890,975 | 80.3% |
| a2 | 181,881 | 2,416,128 | 52,912 | 0.9300 | 476,406 | 2,650,921 | 82.0% |

- a0 逐 case(session-metrics):reuse 0.8764 / 0.8913 / 0.9417 / 0.9112,首 case 最低,符合冷启动。
- **命中率与成本结论相反**:a2 reuse 最高但折算总成本也最高——它做了更多工作(72 turns、每 case 8 条 resource),cached token 按 0.1 计仍累计 24 万成本单位。公平比较需要"成本/有效产出",单看比率或总成本都会误导。
- 注意:a2 批的账单不含 07:57 bootstrap 读 SKILL 的成本(smoke session 里)。
- a1 缺 `session-metrics.json`;a2 的 `session-metrics.json` 只覆盖 smoke session。

## 产物质量(对照 fixture paper.md 逐条核对,无 gold target)

4 个 case 各由一个子代理精读论文全文后按 SKILL 定义核对 precision/recall。**三个 arm 均无幻觉**,分歧全在 recall 与个别分类:

| case | 排序 | 要点 |
|---|---|---|
| eval-low-01 (LCDS) | a0 > a1 > a2 | a2 唯一输的 case:多收的 ROUGE-L 违反 SKILL 明文排除项,且漏 DeepSeek-R1;a0 少而准 |
| eval-low-02 (Dual Quality) | a2 > a0 > a1 | a2 八条全对、两类全覆盖;a0 只收 introduced 类;a1 最差且 paper_type 判错 |
| eval-low-03 (MCMARK) | a1 > a2 > a0 | 必收约 21 项,a1(数据集+模型)与 a2(7 个基线)各拿互补的一半;a0 仅 1 条 |
| eval-low-04 (IRIS) | a2 > a1 > a0 | a2 八条全对;a0/a1 只有 IRIS 一条,a1 还在 warning 里把漏收正当化(误读 SKILL) |

- 按必收项覆盖率粗算:a2 ≈ 50–60%,a1 ≈ 30%,a0 ≈ 25%。
- a2 的盲区有规律:偏向收"方法/基线"类,成块漏"实验材料"类(low-03 的数据集+模型、low-04 的 6 个评测因果图);a1 恰好相反。理想产物约为两臂并集。
- 样本量 4,且混杂了下述 thinking 变量,不能把质量差异直接归因于 shared-root 机制。

## 关键发现:a2 的 eval 批全程 thinking=off(resume 缺陷)

- a2 session 轨迹:bootstrap + smoke-01 有 thinking block,自 smoke-02(首次 `--resume`)起至 eval-low-04 结束 thinking 长度全为 0;a0/a1 每 case 均有 thinking。
- 根因:`deriveSessionContextState` 把未记录的 thinkingLevel 硬编码为 `"off"`(vendored `packages/agent`),而创建时生效的 runtime 默认(medium)从不写入 session;resume 时定型为 off → `enable_thinking=false`。
- widi 回传 API 时**带**完整 think:历史 thinking block 按 `thinkingSignature` 序列化为 assistant 消息的 `reasoning` 字段,且 vllm compat(qwen-chat-template)带 `preserve_thinking: true`。
- case 间无记忆:每 case 回卷到 bootstrap leaf,无 branch summary;shared-root 只是静态前缀复用。

## 修复(已并入 widi main,PR #30)

- `packages/agent`:未记录的 thinkingLevel 由 `"off"` 改为 `null`(resume 回落到 runtime 默认);`prepareCompaction` 增加"有 entry 但无 message 即无可压缩"守卫(stamping 的连带修复)。
- `apps/widi`:新 session(`origin === "new"`)创建时落一条 `thinking_level_change` entry,resume/fork 可回放。
- e06 扩展:`run_started` / `bootstrap_completed` / `bootstrap_resumed` 事件新增 `thinking_level` 字段。
- 验证:`npm run check` ✓;agent-core 248 ✓;apps/widi 1506 ✓。e2e 复跑验证未做。

## 后续候选(未定)

- 用修复后的 widi 重跑 a2 臂(thinking 恢复),与上一批对比。
- 把 4 份参照资源清单固化成 fixture 的 quality target(`case.json` 的 `quality_target_status` 目前是 pending)。
- 扩大到 eval-low-05 / eval-mid / eval-high  strata。
