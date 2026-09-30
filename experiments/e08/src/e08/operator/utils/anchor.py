"""原文锚点：`papers/<key>/paper.md::<章节>::<start>:<end>`。

- 路径相对于论文材料根目录 data/raw/e08-paper-knowledge/。
- 章节用 document.yml outline 的 anchor（如 `S5.SS2`、`A1`），摘要用 `abstract`。
- start:end 是 paper.md 的行号，从 1 起、两端都含，须落在该章节内（章节含其子节）。

行号相对于 document.yml 记录的 markdown_sha256 那一版 paper.md；材料重新生成后锚点需要迁移。
以后给 Agent 的读取工具按同一口径定位。
"""

import os
import re
from functools import cache
from pathlib import Path

import yaml

MATERIALS = Path(os.environ.get("E08_MATERIALS", Path(__file__).resolve().parents[6] / "data/raw/e08-paper-knowledge"))
_ANCHOR = re.compile(r"^(?P<path>papers/[^/]+/paper\.md)::(?P<section>[^:]+)::(?P<start>\d+):(?P<end>\d+)$")
_HEADING = re.compile(r"^(#{1,6}) (.+)$")


@cache
def sections(path: str) -> dict[str, tuple[str, int, int]]:
    """paper.md 的章节：{章节 id: (标题, 起始行, 结束行)}。标题与 outline 按顺序一一对应，只多一个 Abstract；
    outline 中没有 id 的标题不单列。"""
    md = (MATERIALS / path).read_text(encoding="utf-8").splitlines()
    outline = yaml.safe_load((MATERIALS / path).with_name("document.yml").read_text(encoding="utf-8"))["outline"]
    heads = [(i + 1, len(m[1]), m[2].strip()) for i, line in enumerate(md) if (m := _HEADING.match(line))]
    ids = iter(outline)
    out = {}
    for k, (line, level, title) in enumerate(heads):
        if title == "Abstract":
            sid = "abstract"
        else:
            o = next(ids)
            assert o["title"] == title, f"{path}: 第 {line} 行标题 {title!r} 与 outline {o['title']!r} 不对应"
            sid = o["anchor"]
        if sid is None:   # 没有 id 的小标题（如 HippoRAG2 摘要里空的 Keywords:），并入上级章节
            continue
        end = next((l - 1 for l, lv, _ in heads[k + 1:] if lv <= level), len(md))
        out[sid] = (title, line, end)
    return out


def parse_anchor(anchor: str) -> tuple[str, str, int, int] | None:
    m = _ANCHOR.match(anchor)
    return (m["path"], m["section"], int(m["start"]), int(m["end"])) if m else None


def check_anchor(anchor: str) -> list[str]:
    """返回错误列表，空表示锚点可解析且落在所述章节内。"""
    parsed = parse_anchor(anchor) if isinstance(anchor, str) else None
    if not parsed:
        return [f"锚点格式应为 papers/<key>/paper.md::<章节>::<start>:<end>，得到 {anchor!r}"]
    path, section, start, end = parsed
    if not (MATERIALS / path).is_file():
        return [f"锚点文件不存在：{path}"]
    secs = sections(path)
    if section not in secs:
        return [f"{path} 没有章节 {section!r}"]
    title, s, e = secs[section]
    if not s <= start <= end <= e:
        return [f"{anchor}: 行号应在 {section}（{title}）的 {s}:{e} 之内"]
    return []


def read_anchor(anchor: str) -> str:
    """锚点对应的原文。"""
    path, _, start, end = parse_anchor(anchor)
    return "\n".join((MATERIALS / path).read_text(encoding="utf-8").splitlines()[start - 1:end])
