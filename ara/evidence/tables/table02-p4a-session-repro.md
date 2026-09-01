# T02 — 单 session 逐事件复现与 cache 字段观测

**可信度**：自有实测
**Source**: `docs/experiments/p4a.md:18-21`
**支撑**: C01, C02
**日期**: 2026-08-31
**样本**: 随机抽样一条 session，编号 `session_0b334391-...`，对应论文 `2025.acl-long.114`

## 表

| 量 | 值 |
|---|---|
| 对话轮数 | 19 |
| 累计计费 input | 1,893,916 token |
| 最终真实上下文 | 121,499 token |
| **放大倍数** | **15.6x** |
| 全部 19 条 `usage.record` 的 `inputCacheRead` | **0** |
| 全部 19 条 `usage.record` 的 `inputCacheCreation` | **0** |

15.6x 落在 T01 给出的 10–18× 区间内。

## 与 serving 侧的并置（C02 的核心）

同一批运行中，vLLM 侧报 **prefix cache 命中率 89%**（T01）。两个数字同时成立，不矛盾——
它们记的是两本账。见 `../../logic/solution/cache-accounting.md`。

## 未决

> 该 session 全部 19 条 `usage.record` 的 `inputCacheRead` / `inputCacheCreation` 均为 0
> ——**尚未确认是全量数据的普遍现象还是这条样本的个例**，见第 4 节的先决核查项。
>
> —— `docs/experiments/p4a.md:21`

数据资产：`data/raw/kimi-p4a-sessions.tar.gz`，解压后共约 **12,801 个文件**
（`docs/experiments/p4a.md:30`）。这是 **E01** 的数据源。

## 可复现性缺口

分析逻辑**没有落成脚本**，目前不可自动重跑。E01 必须把它脚本化。

> **本表是 B01 的产物，不是本项目实验的结果。** B01 是一次 n=1 的人工复核，
> 见 `../../logic/inherited-observations.md`。
