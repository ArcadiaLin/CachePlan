"""把一步 LLM 调用**逐字**还原成进入模型的 token 序列。

这不是估计量。在 60 份带 ground truth 的 session 上，本模块渲染出的 token 数
与服务端记录的 `prompt_tokens` **完全相等（Δ=0，60/60）**，四个工具集变体都对。
s2 及之前用的 `wire.context_stream()` 是一条「跨 run 可比」的近似流，s3 起改用
本模块，不再使用它。

## 还原链条

kimi-code（OpenAI 兼容路径，`providers/openai-legacy.ts:557`）拼装请求：

    messages = [{role:'system', content: systemPrompt}, ...history]
    tools    = 工具数组，另走 `tools` 字段

vLLM 收到后把 `tools` 里每一项 `model_dump()` 成
`{"type":"function","function":{...}}`，连同 messages 交给模型自带的
`chat_template.jinja` 渲染，再分词。本模块复刻的就是后半段。

## 三个必须一模一样的细节

1. **工具项的 JSON 形状。** 日志里 `llm.tools_snapshot` 记的是扁平的
   `{name, description, parameters}`，但模板里 `tool | tojson` 序列化的是 vLLM
   包装后的 `{"type":"function","function":{...}}`。用扁平形状渲染会稳定偏低
   401 tokens —— 这个差正是 44 个 `{"type": "function", "function": ` 外壳。
2. **`tojson` 不是 jinja2 自带那个。** 自带的 `tojson` 会把 `<` `>` `&` `'`
   转义成 `<` 之类，工具描述里这些字符很多，token 数会变。transformers
   用的是 `json.dumps(..., ensure_ascii=False)`，这里照做。
3. **`trim_blocks` / `lstrip_blocks` 都要开。** transformers 建环境时开着，
   模板里大量 `{%- ... %}` 的空白处理依赖它。

## 分词器

`references/repos/qwen3.6-35b-a3b-tokenizer/`，未纳入版本管理（见 README）。
必须是服务端同一份，换模型必须换它并重跑 `s3_render.py` 的自检。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import provenance

TOKENIZER_DIR = (
    provenance.REPO_ROOT / "references" / "repos" / "qwen3.6-35b-a3b-tokenizer"
)


class RendererUnavailable(RuntimeError):
    """依赖或分词器缺失。调用方应当直接退出，不要退化成字符级估计。"""


def _raise_exception(msg):  # 模板里 raise_exception() 的实现
    raise RuntimeError(msg)


@lru_cache(maxsize=1)
def _template():
    try:
        import jinja2
        import jinja2.ext
        from jinja2.sandbox import ImmutableSandboxedEnvironment
    except ImportError as e:
        raise RendererUnavailable(
            f"缺少 jinja2：{e}。装依赖：uv sync --extra render"
        ) from e

    path = TOKENIZER_DIR / "chat_template.jinja"
    if not path.exists():
        raise RendererUnavailable(
            f"找不到 chat template：{path}。它不在版本管理里，见 README「分词器」。"
        )

    env = ImmutableSandboxedEnvironment(
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=[jinja2.ext.loopcontrols],
    )
    # 见模块文档第 2 点：必须覆盖掉 jinja2 自带的 tojson。
    env.filters["tojson"] = lambda x, indent=None, **kw: json.dumps(
        x, ensure_ascii=False, indent=indent
    )
    env.globals["raise_exception"] = _raise_exception
    return env.from_string(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _tokenizer():
    try:
        from tokenizers import Tokenizer
    except ImportError as e:
        raise RendererUnavailable(
            f"缺少 tokenizers：{e}。装依赖：uv sync --extra render"
        ) from e

    path = TOKENIZER_DIR / "tokenizer.json"
    if not path.exists():
        raise RendererUnavailable(f"找不到分词器：{path}")
    return Tokenizer.from_file(str(path))


def available() -> bool:
    try:
        _template()
        _tokenizer()
        return True
    except RendererUnavailable:
        return False


def wrap_tools(tools: list[dict]) -> list[dict]:
    """日志里的扁平工具项 -> vLLM 交给模板的形状。见模块文档第 1 点。"""
    return [{"type": "function", "function": t} for t in tools]


def render(messages: list[dict], tools: list[dict] | None,
           add_generation_prompt: bool = True) -> str:
    """`tools` 传已经 wrap 过的数组。"""
    return _template().render(
        messages=messages,
        tools=tools,
        add_generation_prompt=add_generation_prompt,
    )


def count(text: str) -> int:
    return len(_tokenizer().encode(text, add_special_tokens=False).ids)


def count_batch(texts: list[str]) -> list[int]:
    """批量分词。tokenizers 的 encode_batch 是多线程的，全语料扫描用这个。"""
    return [len(e.ids) for e in _tokenizer().encode_batch(texts, add_special_tokens=False)]
