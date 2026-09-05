# E06 — P4A-derived WIDI 重执行（已关闭）

**状态：2026-09-05 关闭；不重试、不扩样、不作为直接后续实验。**

## 结论

P4A v1 的原始 session 不适合继续承载 CachePlan 的方法效果评估。它将每篇论文的私有内容很早放入一条长 ReAct session；因此可共享空间主要退化为固定工具/Skill 开头，不能检验“执行组织方式使哪些内容成为共享前缀”。同时，v1 虽有 schema/consistency validation，却没有独立裁定论文理解、资源判断和证据归因的任务质量评测。

原 E06 的设计也不能弥补这些结构性限制：其 static-knowledge 臂使用 Skill 摘要，bootstrap 臂使用完整 Skill，信息内容不等；故两者的差异不能单独归因于 execution-prefix reuse。

## 已运行 pilot 的证据边界

2026-09-03 的 3 臂 × 4 case 串行 pilot 形式上完成，所有 case 都通过既有 validator。其命中率最高的 shared-root/bootstrap 策略，折算总成本也最高；这不是方法收益证据。

该 pilot 还存在不可消除的解释问题：bootstrap 成本未计入、各臂 thinking 配置混杂，且没有独立 gold 或质量 contract。它只留下三条设计教训：不能以 hit ratio 判定收益；bootstrap 必须计入总成本；schema pass 不能替代任务质量。详细重设计与粗略批次报告已从当前文档移除，保留在版本历史中。

## 后续约束

未来若建立受控 workload，应由 [OQ3](../open-questions/Multi-run-workloads.md) 的业务 contract、冻结 fixture、独立质量评测和 workload characterization 先行。其强对照必须是 **full static-first injection**：完整 canonical procedure 与适用 stage/provider contract 以相同信息内容静态注入。任何动态策略只报告相对该强对照的增量，并使用策略名称，不沿用 E06 的臂编号。
