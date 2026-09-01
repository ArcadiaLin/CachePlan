"""kimi-code `wire.jsonl` 的读取与上下文流重建。

这是 E01 全部阶段的共享底座。设计原则只有一条：**不做解释，只做还原**。
判断（哪段是固定知识、哪段是变量）留给下游阶段脚本，这里只忠实标注每段
内容的来源与它进入上下文的顺序。

一份 session 的目录结构（观测所得，非文档）：

    session_<uuid>/
      state.json              会话元数据。注意：约 1671/4083 份的 lastPrompt/title
                              被 redact 过，**不可作为 prompt 的来源**。
      logs/kimi-code.log
      agents/main/wire.jsonl  主 agent 的完整事件流（权威来源）
      agents/agent-N/         子 agent（少见：p90 为 0 个）
      agents/main/tool-results/, tasks/, plans/   旁路产物

`wire.jsonl` 的事件类型（观测所得）：

    metadata                 协议版本
    config.update            携带 systemPrompt / modelAlias / thinkingLevel
    tools.set_active_tools   工具名清单（全语料恒为同一组 27 个）
    permission.set_mode
    turn.prompt              用户输入（**未 redact**）
    context.append_loop_event  event.type ∈ {step.begin, content.part,
                               tool.call, tool.result, step.end}
    usage.record             usageScope=turn 的 token 计数
    context.append_message

其中 `step` 是一次 LLM 调用的序号，一个 step 可以并发多个 tool.call。
文件内的行序即内容进入上下文的顺序 —— 前缀分析依赖这个性质。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import provenance

# state.json 的 prompt 可能被 redact，故 paper id 优先从 wire 的 turn.prompt
# 与首个 Read 的路径参数里取。
PAPER_ID_RE = re.compile(r"20\d\d\.[a-z]+-[a-z]+\.\d+")

# 已知的两个 prompt 家族。其余归为 other 并在清单里逐条列出，不静默丢弃。
FAMILY_PATTERNS = (
    ("extract", "Read this UTF-8 prompt file and follow its instructions exactly"),
    ("repair", "You are repairing one ACL 2025 reference-extraction record"),
)


@dataclass
class Segment:
    """一段进入上下文的内容，按进入顺序排列。"""

    kind: str            # system | user | assistant_text | tool_call | tool_result
    text: str
    step: int | None = None
    tool: str | None = None
    call_id: str | None = None


@dataclass
class Usage:
    step: int | None
    input_other: int
    output: int
    cache_read: int
    cache_creation: int
    # 「字段缺失」与「字段存在且为 0」对闸门是实质区别：前者说明 harness
    # 根本没上报，后者说明它上报了、值确实是零。必须分开记。
    has_cache_fields: bool = False


@dataclass
class Session:
    sid: str
    path: Path
    created_at: str | None = None
    updated_at: str | None = None
    model: str | None = None
    thinking: str | None = None
    system_prompt: str | None = None
    active_tools: list[str] = field(default_factory=list)
    user_prompt: str | None = None
    family: str = "other"
    paper_id: str | None = None
    n_user_prompts: int = 0
    n_subagent_dirs: int = 0
    steps: list[int] = field(default_factory=list)
    turns: list[int] = field(default_factory=list)
    tool_calls: list[tuple[int | None, str, str]] = field(default_factory=list)
    usage: list[Usage] = field(default_factory=list)
    finish_reasons: dict[str, int] = field(default_factory=dict)
    ttft_ms: list[int] = field(default_factory=list)
    stream_ms: list[int] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # ---- 便捷派生量 ----
    @property
    def n_steps(self) -> int:
        return len(self.steps)

    @property
    def n_tools(self) -> int:
        return len(self.tool_calls)

    @property
    def tool_seq(self) -> list[str]:
        return [t[1] for t in self.tool_calls]

    @property
    def sum_input(self) -> int:
        return sum(u.input_other for u in self.usage)

    @property
    def peak_input(self) -> int:
        return max((u.input_other for u in self.usage), default=0)

    @property
    def cache_nonzero(self) -> int:
        return sum(1 for u in self.usage if u.cache_read or u.cache_creation)


def _as_text(value) -> str:
    """turn.prompt 的 input 可能是 str，也可能是 [{type:text,text:...}]。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for p in value:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text") or "")
            else:
                parts.append(json.dumps(p, ensure_ascii=False))
        return "\n".join(parts)
    return json.dumps(value, ensure_ascii=False)


def classify_family(prompt: str) -> str:
    for name, pat in FAMILY_PATTERNS:
        if prompt.lstrip().startswith(pat):
            return name
    return "other"


def session_dirs(root: Path | None = None) -> list[Path]:
    root = root or provenance.RAW_ROOT
    out: list[Path] = []
    for wd in sorted(root.glob("wd_*")):
        out.extend(sorted(wd.glob("session_*")))
    return out


def load(sdir: Path, with_segments: bool = False) -> Session:
    """读一份 session。

    `with_segments=False` 时不保留正文，只留统计量 —— 全语料扫描用这个，
    内存占用可忽略。阶段 3 的前缀分析才需要 `with_segments=True`。
    """
    s = Session(sid=sdir.name, path=sdir)

    state_path = sdir / "state.json"
    if state_path.exists():
        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
            s.created_at = st.get("createdAt")
            s.updated_at = st.get("updatedAt")
        except Exception as e:  # 元数据坏了不应让整份 session 不可用
            s.errors.append(f"state.json: {e}")

    s.n_subagent_dirs = len(list((sdir / "agents").glob("agent-*"))) if (sdir / "agents").exists() else 0

    wf = sdir / "agents" / "main" / "wire.jsonl"
    if not wf.exists():
        s.errors.append("wire.jsonl missing")
        return s

    calls: dict[str, tuple[str, str]] = {}
    steps: set[int] = set()
    turns: set[int] = set()

    try:
        with open(wf, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    s.errors.append("bad json line")
                    continue
                t = o.get("type")

                if t == "config.update":
                    if o.get("systemPrompt") is not None:
                        s.system_prompt = o["systemPrompt"]
                        if with_segments:
                            s.segments.append(Segment("system", o["systemPrompt"]))
                    if o.get("thinkingLevel") is not None:
                        s.thinking = o["thinkingLevel"]

                elif t == "tools.set_active_tools":
                    s.active_tools = list(o.get("names") or [])

                elif t == "turn.prompt":
                    text = _as_text(o.get("input"))
                    s.n_user_prompts += 1
                    if s.user_prompt is None:
                        s.user_prompt = text
                        s.family = classify_family(text)
                        m = PAPER_ID_RE.search(text)
                        if m:
                            s.paper_id = m.group(0)
                    if with_segments:
                        s.segments.append(Segment("user", text))

                elif t == "usage.record":
                    s.model = o.get("model") or s.model

                elif t == "context.append_loop_event":
                    e = o.get("event") or {}
                    et = e.get("type")
                    if e.get("step") is not None:
                        steps.add(e["step"])
                    if e.get("turnId") is not None:
                        turns.add(e["turnId"])

                    if et == "content.part":
                        part = e.get("part") or {}
                        text = part.get("text") or ""
                        if with_segments:
                            s.segments.append(
                                Segment("assistant_text", text, step=e.get("step"))
                            )

                    elif et == "tool.call":
                        cid = e.get("toolCallId")
                        name = e.get("name") or "?"
                        args = json.dumps(e.get("args"), ensure_ascii=False, sort_keys=True)
                        calls[cid] = (name, args)
                        s.tool_calls.append((e.get("step"), name, args))
                        if s.paper_id is None:
                            m = PAPER_ID_RE.search(args)
                            if m:
                                s.paper_id = m.group(0)
                        if with_segments:
                            s.segments.append(
                                Segment("tool_call", args, step=e.get("step"),
                                        tool=name, call_id=cid)
                            )

                    elif et == "tool.result":
                        cid = e.get("toolCallId")
                        name = calls.get(cid, ("?", ""))[0]
                        text = json.dumps(e.get("result"), ensure_ascii=False)
                        if with_segments:
                            s.segments.append(
                                Segment("tool_result", text, tool=name, call_id=cid)
                            )

                    elif et == "step.end":
                        u = e.get("usage") or {}
                        s.usage.append(
                            Usage(
                                step=e.get("step"),
                                input_other=u.get("inputOther", 0) or 0,
                                output=u.get("output", 0) or 0,
                                cache_read=u.get("inputCacheRead", 0) or 0,
                                cache_creation=u.get("inputCacheCreation", 0) or 0,
                                has_cache_fields=(
                                    "inputCacheRead" in u or "inputCacheCreation" in u
                                ),
                            )
                        )
                        fr = e.get("finishReason")
                        if fr:
                            s.finish_reasons[fr] = s.finish_reasons.get(fr, 0) + 1
                        if e.get("llmFirstTokenLatencyMs") is not None:
                            s.ttft_ms.append(e["llmFirstTokenLatencyMs"])
                        if e.get("llmStreamDurationMs") is not None:
                            s.stream_ms.append(e["llmStreamDurationMs"])
    except Exception as e:
        s.errors.append(f"wire.jsonl: {e}")

    s.steps = sorted(steps)
    s.turns = sorted(turns)
    return s


def context_stream(s: Session) -> str:
    """把 segments 拼成一条字节流。

    **这不是发给模型的真实 prompt**：工具 schema（约 18K tokens，见 README）
    不在日志里，各段之间的模板/分隔符也无从得知。它是「同一 harness 下、
    跨 run 可比」的一条重建流 —— 前缀分析只依赖它在各 run 之间的可比性，
    不依赖它与真实 prompt 逐字相同。
    """
    return "".join(seg.text for seg in s.segments)
