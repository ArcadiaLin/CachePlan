# Artifacts

指针索引，指向仓库内**已存在**的代码。CachePlan 自身的方法代码尚不存在，因此本索引全部是
P4A 这个历史项目的代码——它按 `constraints.md` 第 1 条是**只读**的。

> **本层的重要发现**：编译本 artifact 时，`docs/` 完全没有记录 `layer4_v2/` 的存在，
> 而这套代码是 autonomy ladder 上一个已经实现并评估过的臂（见下方 §3）。
> **2026-09-01 已把它补记进 `docs/PROGRESS.md` 的 Experiments 节**，并按定位纠正记为
> 继承观测 B02（P4A 自己的工程验收），不是本项目的实验。
> `docs/PROGRESS.md:36` 仍把 controlled comparison 列为待办，这是正确的——B02 不构成
> 那个受控实验。**处置方式仍待用户裁定**，见 `../trace/exploration_tree.yaml` 的
> `n11-docs-code-drift`。

---

## 1. 固定 procedural knowledge（Skill）

跨 run **逐字相同**的那部分——按 `workload-definition.md` 的判据 1，这是本项目全部研究空间
的来源。

| 文件 | 规模 | 用于 |
|---|---|---|
| `experiments/p4a/skill/paper-mineru-resource-extract/SKILL.md` | 460 行 / 21,014 字节 | v1 主链（MinerU 路线，现网实际使用） |
| `experiments/p4a/skill/paper-latex-resource-extract/SKILL.md` | 224 行 / 8,964 字节 | LaTeX 路线 |
| `.../paper-latex-resource-extract/references/workflow.md` | — | 流程细则 |
| `.../paper-latex-resource-extract/references/field_guide.md` | — | 字段语义 |
| `.../paper-latex-resource-extract/references/parser_extension_guide.md` | — | 解析器扩展 |

21,014 字节的 MinerU Skill 是 P4A 里最大的一块固定前缀候选。**它当前不在 prompt 前缀里**
——见 §2 的 C10。

## 2. v1：Full ReAct Agent 臂（autonomy ladder L4）

| 文件 | 行数 | 职责 |
|---|---|---|
| `src/extract/layer4/launch_kimi_layer4.py` | 951 | 批量编排器；起 kimi-code CLI、写 repair prompt、重试 |
| `src/extract/layer4/prepare_mineru_layer4.py` | 326 | 逐篇生成 `agent_prompt.md` 与模板产物 |
| `src/extract/layer4/apply_agent_judgment.py` | 524 | 把 `agent_judgment.json` 落成 YAML |
| `src/extract/layer4/validate_layer4_outputs.py` | 373 | validator（validation-and-repair 循环的判据来源） |
| `src/extract/layer4/common.py` | 309 | 共享工具 |

### 上下文构造顺序（C10 的证据）

v1 **不把 Skill 放进 prompt**，而是让 agent 用工具去读它：

```
[kimi CLI 固定 system prompt]                        ← 跨 run 相同
[user: "Read this UTF-8 prompt file ...: <per-paper path>"]  ← 从这里开始逐 run 不同
[tool result: agent_prompt.md 内容]                   ← 逐篇生成，per-run
[tool result: SKILL.md 内容（21KB，跨 run 逐字相同）]    ← 固定内容，但排在 per-run 内容之后
```

于是那 21KB 的固定 procedural knowledge 对**跨 run 前缀复用的贡献为 0**——不是因为它不同，
而是因为它排在后面。这正是 `cache-accounting.md` §5 描述的 cache-hostile ordering，
**在本项目自己的代码里**。

**Sources**
- 指向 per-paper 路径而非内联 Skill ← `experiments/p4a/src/extract/layer4/launch_kimi_layer4.py:423` «"Read this UTF-8 prompt file and follow its instructions exactly:\n"» [input]
- 传的是逐篇生成文件的路径 ← `experiments/p4a/src/extract/layer4/launch_kimi_layer4.py:424` «f"{repo_relative(prompt_path)}\n\n"» [input]
- skill 靠名字由 agent 自取 ← `experiments/p4a/src/extract/layer4/launch_kimi_layer4.py:425` «"Use the named skill from the prompt. Construct or repair agent_judgment.json, "» [input]
- 让 agent 自己读 SKILL.md ← `experiments/p4a/src/extract/layer4/launch_kimi_layer4.py:555-556` «- Before repairing, read and follow this skill file:\n  skill/paper-mineru-resource-extract/SKILL.md» [input]
- `agent_prompt.md` 是逐篇生成的 ← `experiments/p4a/src/extract/layer4/prepare_mineru_layer4.py:319` «(output_dir / "agent_prompt.md").write_text(build_agent_prompt(bundle), encoding="utf-8")» [input]

## 3. v2：Workflow + LLM Nodes + Repair 臂（autonomy ladder ≈L2–L3）

`refractor.md` 的重构方案**已经完整实现**。这是 `docs/` 里完全没提到的事实。

| 文件 | 行数 | 对应 refractor.md |
|---|---|---|
| `src/extract/layer4_v2/launch_layer4_v2.py` | 506 | §4 编排与状态机 |
| `src/extract/layer4_v2/build_paper_inputs.py` | 277 | §2.2 引文链降级 + §2.3 文档预处理 |
| `src/extract/layer4_v2/run_candidate_extraction.py` | 134 | §2.4 调用 1 |
| `src/extract/layer4_v2/resolve_external_resources.py` | 463 | §2.5 外部验证缓存 |
| `src/extract/layer4_v2/run_final_judgment.py` | 233 | §2.6 调用 2 |
| `src/extract/layer4_v2/prompts.py` | 229 | 两次调用的静态 prompt 块 |
| `src/extract/layer4_v2/schemas.py` | 193 | guided decoding 的 JSON schema |
| `src/extract/layer4_v2/llm_client.py` | 149 | vLLM 客户端（采集 `prompt_tokens`/`completion_tokens`） |
| `src/extract/layer4_v2/common_v2.py` | 135 | 共享工具 |
| `src/extract/layer4_v2/compare_v1_v2.py` | 128 | §7 v1/v2 逐篇 diff |
| `src/extract/layer4_v2/adjudicate_compare.py` | 87 | §7 分歧裁定 |
| `src/extract/layer4_v2/README.md` | — | 使用说明与评估结论 |

### 这套代码里已有一个自觉的跨 run 前缀设计（C11 的证据）

`prompts.py` 的模块 docstring 明写：

> The static blocks must stay byte-identical across papers so vLLM prefix
> caching turns them into a shared cached prefix.

即：**本项目关心的那个杠杆，在自己的代码里已经被自觉使用过一次**。但 `llm_client.py` 只
采集 `prompt_tokens` / `completion_tokens`，**没有采集任何 cache 相关字段**——用了这个
杠杆，却没有测量它。

**Sources**
- ← `experiments/p4a/src/extract/layer4_v2/prompts.py:4-5` «The static blocks must stay byte-identical across papers so vLLM prefix\ncaching turns them into a shared cached prefix.» [input]
- ← `experiments/p4a/src/extract/layer4_v2/README.md:25` «- **两次 LLM 调用**都打到本地 vLLM（见 §5），字节级一致的静态前缀以吃 prefix cache。» [input]
- 只采集 token 数不采集 cache ← `experiments/p4a/src/extract/layer4_v2/llm_client.py:138-139` «"prompt_tokens": getattr(usage, "prompt_tokens", None),\n                "completion_tokens": getattr(usage, "completion_tokens", None),» [input]

### v1 兜底：两臂并非完全独立

v2 的失败路径会**回退到 v1 的 ReAct agent**（`merged_via_fallback`），再失败才
`blocked_v2_manual`。因此把 v1/v2 当作 autonomy ladder 的两个独立臂时，**v2 臂里混入了
一部分 v1 的执行**，兜底率必须作为协变量报告。

## 4. 上游流水线（两臂共享，不构成对照变量）

| 路径 | 职责 |
|---|---|
| `src/run_pipeline.py` (451 行) | 单篇端到端编排：MinerU → references → cite contexts → Layer4 |
| `src/acl-mirror/download_acl_year.py`, `create_mirror.py` | ACL PDF 镜像 |
| `src/mineru/batch_process_acl_mineru.py`, `process_pdf_with_mineru.py` | MinerU OCR |
| `src/mineru/serve_mineru_vllm.sh`, `mineru_vllm_proxy.py` | MinerU VLM 服务 |
| `src/mineru/repair_references.py` | 引用修复 |
| `src/extract/references/extract_mineru_references.py` | 单篇 references 抽取 |
| `src/extract/references/compare_mineru_reference_sources.py` | 双源校验（失败 → `blocked_reference_mismatch`） |
| `src/extract/references/extract_cite_contexts.py` | citation context |
| `src/extract/references/run_reference_pipeline.py` | 全量汇总（审计用，**不再阻塞 Layer4**） |
| `src/extract/references/build_reference_index.py`, `update_reference_record.py` | 索引与记录更新 |
| `src/extract/references/launch_kimi_reference_repairs.py` | 引用修复的 agent 路径 |

## 5. 配置与基础设施

| 路径 | 内容 |
|---|---|
| `infra/vllm/docker-compose-qwen36-35B.yml` | vLLM serving 配置（`environment.md` 里那套参数的出处） |
| `infra/kimi/config.toml`, `infra/kimi/mcp.json` | kimi-code CLI 配置与 MCP 工具定义 |
| `agent/referneces-repair-agent/agent.yaml`, `system.md` | 引用修复 agent 的定义 |
| `skill/paper-latex-resource-extract/scripts/config/layer4_config.yml` | Layer4 配置 |
| `pyproject.toml`, `uv.lock`, `.python-version` | Python 环境 |

## 6. Skill 附带的脚本（LLM 不写、程序执行的部分）

`skill/paper-latex-resource-extract/scripts/` 下 15 个 Python 文件：
`apply_agent_judgment.py`、`arxiv_metadata_client.py`、`bib_reference_resolver.py`、
`citation_context_locator.py`、`common.py`、`figure_asset_extractor.py`、
`latex_structure_parser.py`、`latex_unpack.py`、`parse_batch.py`、`parse_one.py`、
`resource_mention_extractor.py`、`script_config.py`、`supplement_runner.py`、
`yaml_emitter.py`、`yaml_linter.py`。

这些是 open question 里"确定性的、可 workflow 化的"那部分的既有实现——做 E02 时
L1/L2 臂应当直接复用它们，而不是重写。

## 7. 不在本仓库、但被引用的产物

| 产物 | 位置 | 影响 |
|---|---|---|
| `reports/layer4_v2_eval200.md` | p4a 工作副本（`/home/lzx/projs/p4a_v2`），**不在本仓库** | 200 篇评估的完整报告；本 artifact 只能转引 README 里的摘要数字，**未经核实** |
| `/srv/datasets/p4a/data/processed/layer4{,_v2}/` | 现网数据根 | v1/v2 的全部逐篇产物 |
| `data/raw/kimi-p4a-sessions.tar.gz` | 本仓库但 gitignored | session 日志，B01 与 E01 的数据源 |
