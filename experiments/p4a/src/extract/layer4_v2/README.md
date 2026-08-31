# Layer4 v2 抽取流程（程序批处理 + 两次 LLM 调用）

Layer4 资源抽取的重构版。用**程序化批处理 + 两次纯文本 LLM 调用**替代 v1 的"每篇一个 Kimi ReAct agent"。
设计原理见仓库根 [`refractor.md`](../../../refractor.md)，200 篇对照评估见
[`reports/layer4_v2_eval200.md`](../../../reports/layer4_v2_eval200.md)。本文只讲**怎么用**。

> v1（旧 ReAct agent 流程）在 `src/extract/layer4/`，输出树 `processed/layer4/`。
> v2 是独立副本，**从不改写 v1 的代码或产物**。

---

## 1. 架构一图流

每篇论文按固定阶段串行推进（阶段间幂等，续跑时已完成阶段自动跳过）：

```
引文链(软门禁,现建或降级)
  └─ build_paper_inputs      程序：切正文/去参考文献、挖 URL(含 content_list 脚注)、压缩图表注
      └─ 调用1 candidate      LLM：抽语义候选(thinking OFF)          → semantic_candidates.json
          └─ resolve          程序：GitHub/HF/arXiv/URL 验证 + 全局缓存 → external_resolution.json
              └─ 调用2 judge   LLM：保留/丢弃/定 kind·relation(thinking ON) → agent_judgment.json
                  └─ apply+validate  复用 v1 脚本落 YAML          → resource_records.yml 等
```

- **两次 LLM 调用**都打到本地 vLLM（见 §5），字节级一致的静态前缀以吃 prefix cache。
- validate 失败 → 轻量修补调用 ×2 → 仍失败则回退 **v1 ReAct agent 兜底**（落到 v2 树）→ 再失败标 `blocked_v2_manual`。

---

## 2. 怎么跑

统一从**仓库根**运行，用副本自己的 venv。外网访问相关的环境变量务必先设好（§5）。

```bash
cd /home/lzx/projs/p4a_v2
export NO_PROXY="127.0.0.1,localhost,192.168.163.112,::1"; export no_proxy="$NO_PROXY"

# 全量（读 references JSONL，自动跳过前言/proceedings）
.venv/bin/python src/extract/layer4_v2/launch_layer4_v2.py --workers 12 --llm-concurrency 8

# 指定清单（每行一个 paper_id，# 注释；见 §6 关于前言过滤的坑）
.venv/bin/python src/extract/layer4_v2/launch_layer4_v2.py \
  --paper-id-file /path/to/ids.txt --workers 12 --llm-concurrency 8

# 单篇 / 少量（调试）
.venv/bin/python src/extract/layer4_v2/launch_layer4_v2.py --paper-id 2026.acl-long.123
```

长批次建议挂后台（`run_in_background` 或 `nohup ... > run.log 2>&1 &`），避免前台超时。

### 常用参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--paper-id` | — | 指定单篇，可重复 |
| `--paper-id-file` | — | 清单文件，可重复。**给了清单会跳过内置前言过滤（§6）** |
| `--venue-filter` | `""` | paper_id 子串过滤，如 `acl-long.` |
| `--limit N` | — | 只取前 N 篇 |
| `--workers` | 12 | 每篇管线的并发 worker 数 |
| `--llm-concurrency` | 8 | LLM 请求并发（GPU 独占时可上调） |
| `--force` | off | 无视已有产物，全阶段重做 |
| `--skip-cite-chain` | off | 不现建引文链，直接用正则降级上下文 |
| `--no-repair-references` | — | 关掉引文链的 Kimi 修补（默认开） |
| `--include-front-matter` | — | 不跳过前言（默认跳） |
| `--refresh-cache` | off | 强制重查外部验证缓存 |
| `--no-fallback` | off | 关掉 v1 agent 兜底 |
| `--references-jsonl` / `--output-root` / `--cache-root` | 见 §5 | 覆盖默认路径 |

批次结束打印 `batch_report.json` 汇总（各状态计数、耗时、token 计量），失败清单见 `batch_failures.json`。

---

## 3. 输出与「怎么区分 v1/v2」

v2 产物写在**独立输出树**：

```
/srv/datasets/p4a/data/processed/layer4_v2/<year>/<venue>/<paper_id>/
```

对比 v1 的 `processed/layer4/<year>/<venue>/<paper_id>/`——**目录带 `_v2` 就是 v2 跑的**，v2 从不碰 v1 的树。

**两重区分标记：**
1. **输出树**：`layer4_v2/` vs `layer4/`。
2. **`v2_state.json`**：每篇 v2 产物目录里都有这个状态机文件（记 `status`/`citation_source`/各阶段耗时），**v1 产物里没有**。按篇判定是不是 v2 跑的，看有没有 `v2_state.json` 即可。

每篇主要产物：

| 文件 | 内容 |
|---|---|
| `v2_state.json` | 状态机（见 §4），**v2 专属标记** |
| `paper_index.json` / `fulltext_for_llm.md` / `url_mentions.json` / `captions.json` | 程序预处理输入 |
| `semantic_candidates.json` | 调用1 语义候选 |
| `external_resolution.json` | 外部验证结果 |
| `agent_judgment.json` | 调用2 最终裁判 |
| `resource_records.yml` / `paper_record.yml` / `quality_report.json` | 兼容 v1 的最终产物（apply 脚本生成） |

全局验证缓存（跨论文共享）：`processed/layer4_v2/cache/{github,huggingface,hf_search,github_search,arxiv,url_status}.jsonl`。

---

## 4. 状态机（`v2_state.json` 的 `status`）

正常推进：`prepared → inputs_built → candidates_done → verified → judged → merged`

批次结果里每篇的终态：

| 终态 | 含义 |
|---|---|
| `merged` | 正常完成，产物已落 YAML 并通过 validate |
| `merged_via_fallback` | v2 主链失败，回退 v1 ReAct agent 兜底后完成 |
| `skipped_merged` | 已是 merged，幂等跳过（除非 `--force`） |
| `blocked_v2_manual` | 修补 ×2 + 兜底都失败，需人工介入 |
| `error` | 未捕获异常（如调用1 输出超 `--max-tokens` 截断） |

**续跑**：直接重跑同一命令即可，已 merged 的跳过、未完成的从断点续。想强制重做某几篇用 `--force` + `--paper-id`。

---

## 5. 环境与依赖

- **vLLM 端点**：`http://192.168.163.112:8003/v1`（模型运行时自动探测；`api_key=EMPTY`）。
  客户端 `trust_env=False`，**永不**为本地 vLLM 走代理——所以 `NO_PROXY` 必须含 `192.168.163.112`。
- **外网访问**（GitHub/HF/普通 URL）统一走代理 `http://127.0.0.1:7899`；arXiv 直连优先。
- **GitHub token**：从环境变量 `GITHUB_PAT_TOKEN`（回退 `GITHUB_TOKEN`）读，用于抬高 GitHub API 限速；无 token 会匿名+强限速。
- **默认数据路径**（可用 CLI 覆盖）：
  - references：`processed/cite/2026/acl/acl2026_verified_plus_repaired.jsonl`
  - 输出树：`processed/layer4_v2/2026/acl`
  - 缓存：`processed/layer4_v2/cache`
- 运行前 `export NO_PROXY="127.0.0.1,localhost,192.168.163.112,::1"`（含 `no_proxy` 小写）。

---

## 6. 选篇范围与两个坑

**当前 MinerU 覆盖**（2026-07）：ACL 主会两年 + 2026 大量非 acl venue。v1 历史上只做了**两年的 ACL 主会**
（2025/acl ≈1969、2026/acl =1351）；eacl/findings/propor/workshops 等**从未跑过**。跑批前先按 `年份×venue`
核对 MinerU 有多少、v1/v2 已做多少、剩多少，再定清单。

**坑 1 — `--paper-id-file` 绕过前言过滤。** 内置 `is_probable_front_matter` 只在**不给清单**时生效。
自建清单时，proceedings 前言卷（标题如 "Proceedings of the Conference"、"The 64th Annual Meeting…"、
"... : Long Papers"，paper_id 常是 `<venue>.0`）不会被自动剔除——它们能 merged 但资源为 0。
自建清单请先按 MinerU 标题过滤掉前言。

**坑 2 — 引文链软门禁。** v1 引文链只给 ACL 建过。对引文链不全的论文，v2 默认会**现建**
（跑 v1 的 `extract_mineru_references` + `compare`，必要时 Kimi 修补），失败才**降级**成正则引文上下文
（`citation_source=degraded`）。想跳过现建、直接降级用 `--skip-cite-chain`（更快，但引文相关证据更弱）。

---

## 7. 评估与复评

对已有 v1 产物的论文可做对照评估：

```bash
# 逐篇 diff v1/v2 资源(name/kind/relation)，产出 compare JSON
.venv/bin/python src/extract/layer4_v2/compare_v1_v2.py --paper-id-file <ids> --report compare.json
# 裁定：模糊名/URL 救回、通用依赖/闭源模型/伪影分桶，算裁定召回
.venv/bin/python src/extract/layer4_v2/adjudicate_compare.py compare.json
```

§8 通过线（详见评估报告）：v1 召回≥95%、kind/relation 一致率≥90%、schema 100%、兜底率≤5%、≤60s/篇。
200 篇评估裁定召回 96.1% 通过。**注意**：全新数据（v1 没做过的 venue/年份）没有 v1 对照，只能报管线健康度
（merged/schema/兜底率），无法给召回对照。
