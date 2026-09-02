"""把 `wire.jsonl` 回放成每一步真正发给模型的 messages 数组。

`render.py` 负责「messages + tools -> token 序列」，本模块负责它的上游：
「事件流 -> messages」。两者合起来就是完整的还原链条。

## 回放规则

按文件行序回放，维护一个消息列表，在每个 `step.begin` 处快照 —— 那份快照就是
这一步的请求。行序即入上下文的顺序，这是 wire.jsonl 的设计性质。

    context.append_message   直接追加（harness 注入的提醒也走这里，role=user）
    step.begin               快照当前列表 = 本步请求
    content.part             攒着，作为 assistant 消息的正文
    tool.call                攒着，作为 assistant 消息的 tool_calls
    tool.result              攒着
    step.end                 追加 assistant 消息，再按调用顺序追加各 tool 消息

## 工具结果的渲染规则不是猜的

日志里存的是**事实**（`output` / `isError` / `note`），不是模型看到的文本。
两者之间隔着 `renderToolResultForModel`
（`packages/agent-core/src/agent/context/tool-result-render.ts`），本模块照抄它：

- `isError` 为真时，前面无条件加一行 `<system>ERROR: ...</system>`；
- 输出为空（或恰好是 `Tool output is empty.`）时换成占位符；
- `note` 用换行接在后面，不加任何包装。

漏掉其中任何一条，Δ 就对不上：只补 `note` 时 11 步里对 6 步，`isError` 那条
差 12 tokens。三条都照抄之后，60 份 ground-truth session 的**每一步**都 Δ=0。

## 推理内容

全语料的 `content.part` 只有 `text` 一种类型，没有 `think`。这不是日志缺失 ——
若当时把 reasoning 回传给了模型，重建值会系统性偏低，而实测是每一步都精确
相等。所以这些 run 没有把推理内容放回上下文。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# 照抄 tool-result-render.ts 的常量。改动必须同步，并重跑 s3 自检。
TOOL_ERROR_STATUS = "<system>ERROR: Tool execution failed.</system>"
TOOL_EMPTY_STATUS = "<system>Tool output is empty.</system>"
TOOL_EMPTY_ERROR_STATUS = (
    "<system>ERROR: Tool execution failed. Tool output is empty.</system>"
)
TOOL_OUTPUT_EMPTY_TEXT = "Tool output is empty."


def render_tool_result(result) -> str:
    """存下来的事实 -> 模型实际看到的文本。见模块文档。"""
    if not isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)

    out = result.get("output") or ""
    if not isinstance(out, str):
        out = json.dumps(out, ensure_ascii=False)

    if result.get("isError") is True:
        text = TOOL_EMPTY_ERROR_STATUS if not out else f"{TOOL_ERROR_STATUS}\n{out}"
    elif out.strip() == "" or out.strip() == TOOL_OUTPUT_EMPTY_TEXT:
        text = TOOL_EMPTY_STATUS
    else:
        text = out

    note = result.get("note")
    if note:
        text = f"{text}\n{note}"
    return text


@dataclass
class StepRequest:
    """一次 LLM 调用的请求。`messages` 不含 system，由调用方拼在最前。"""

    step: int | None
    messages: list[dict]
    prompt_tokens: int | None = None   # 服务端算的，Δ oracle 的那一侧


@dataclass
class SessionContext:
    sid: str
    system_prompt: str | None = None
    # 仅 60/4083 份的日志里有工具 schema；其余要由调用方指定一套。
    tools: list[dict] | None = None
    tools_hash: str | None = None
    steps: list[StepRequest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build(sdir: Path) -> SessionContext:
    ctx = SessionContext(sid=sdir.name)
    wf = sdir / "agents" / "main" / "wire.jsonl"
    if not wf.exists():
        ctx.errors.append("wire.jsonl missing")
        return ctx

    msgs: list[dict] = []
    text_parts: list[str] = []
    calls: list[dict] = []
    results: dict[str, object] = {}

    def flush_step() -> None:
        """一步生成结束：assistant 消息，再按调用顺序追加 tool 消息。"""
        nonlocal text_parts, calls, results
        m: dict = {"role": "assistant", "content": "".join(text_parts)}
        if calls:
            m["tool_calls"] = calls
        msgs.append(m)
        for c in calls:
            msgs.append({
                "role": "tool",
                "tool_call_id": c["id"],
                "content": render_tool_result(results.get(c["id"])),
            })
        text_parts, calls, results = [], [], {}

    with open(wf, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                ctx.errors.append("bad json line")
                continue
            t = o.get("type")

            if t == "config.update" and o.get("systemPrompt") is not None:
                ctx.system_prompt = o["systemPrompt"]
            elif t == "llm.tools_snapshot" and ctx.tools is None:
                ctx.tools = o.get("tools")
                ctx.tools_hash = o.get("hash")
            elif t == "context.append_message":
                m = o.get("message") or {}
                msgs.append({"role": m.get("role"), "content": m.get("content")})
            elif t == "context.append_loop_event":
                e = o.get("event") or {}
                et = e.get("type")
                if et == "step.begin":
                    ctx.steps.append(StepRequest(step=e.get("step"), messages=list(msgs)))
                    text_parts, calls, results = [], [], {}
                elif et == "content.part":
                    p = e.get("part") or {}
                    if p.get("type") == "text":
                        text_parts.append(p.get("text") or "")
                elif et == "tool.call":
                    calls.append({
                        "id": e.get("toolCallId"),
                        "type": "function",
                        # 模板对 arguments 做 |items 迭代，必须是 dict 不是 JSON 串
                        "function": {"name": e.get("name"), "arguments": e.get("args") or {}},
                    })
                elif et == "tool.result":
                    results[e.get("toolCallId")] = e.get("result")
                elif et == "step.end":
                    if ctx.steps and ctx.steps[-1].step == e.get("step"):
                        # 历史数据 cached 恒为 0，故 inputOther 即 prompt_tokens
                        ctx.steps[-1].prompt_tokens = (e.get("usage") or {}).get("inputOther")
                    flush_step()

    return ctx


def messages_for(ctx: SessionContext, step: StepRequest) -> list[dict]:
    """加上 system 消息，得到 kimi-code 实际发出的 messages 数组。

    形状见 `providers/openai-legacy.ts:557`：systemPrompt 作为 messages[0]。
    openai 路径上没有 mergeConsecutiveUserMessages，相邻 user 消息不合并。
    """
    out: list[dict] = []
    if ctx.system_prompt:
        out.append({"role": "system", "content": ctx.system_prompt})
    out.extend(step.messages)
    return out
