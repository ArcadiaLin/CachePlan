"""阶段 0b：把每份 session 的前缀拆成块，给出它落在哪一类。

s0 只记了 `sysprompt_chars` 这一个不透明的代理量。本阶段回答它代理的是什么：
systemPrompt 不是一整块，而是若干**生命周期不同**的块拼起来的 ——

    (preamble)                     harness 自带，全语料逐字相同
    # Prompt and Tool Use          harness 自带，换版本才变
    # General Guidelines ...       同上
    # Working Environment
    ## Operating System            机器属性
    ## Date and Time               **每 run 都变**（时间戳）
    ## Working Directory + 目录树    操作者动一次目录就变
    # Project Information          操作者的 AGENTS.md
    # Skills / ## Available skills 注册了哪些 skill
    # Ultimate Reminders           harness 自带

跨 run 前缀能共享到哪个字节，由这些块里**最靠前的那个不同的块**决定。所以划分
session 的依据必须按块来定义，而不是按整段 systemPrompt 的长度或哈希。

产物：
    data/processed/e01/s0b_prompt_blocks.jsonl   一行一份 session
    data/processed/e01/s0b_summary.json          各轴基数、联合分布、时间戳损耗

用法：
    uv run -m e01.s0b_prompt_blocks [--limit N]
"""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter, defaultdict

from . import provenance, wire

SCRIPT = "e01/s0b_prompt_blocks.py"

# systemPrompt 的块边界：一级或二级 markdown 标题。标题行本身归入下一块的块名，
# 不进块体 —— 这样块体的哈希不受标题措辞影响。
BLOCK_HEAD = re.compile(r"^#{1,2} (.+)$")
PREAMBLE = "(preamble)"

# 各轴取哪一块。留在 OTHER 里的块（preamble、Prompt and Tool Use、General
# Guidelines、Skills、Ultimate Reminders、Operating System 等）合起来当作 harness
# 签名 —— 包括某个块**是否存在**，因为块名也进哈希。
AXIS_BLOCK = {
    "timestamp": "Date and Time",
    "tree": "Working Directory",
    "agents": "Project Information",
    "skills": "Available skills",
}
# 机器属性块。它不随 harness 版本走，但全语料只有一个取值，单列出来免得
# 混进 harness 签名后让"harness 换代"这个说法失去意义。
MACHINE_BLOCKS = ("Operating System",)

# 首条 user message 的投递形态。这两个前缀与 wire.FAMILY_PATTERNS 用的是同一组
# 判据 —— 也就是说现在的 `family` 标签同时编码了「任务类型」和「任务怎么送进
# 上下文」这两件不同的事，见 s0b_summary 的 delivery_vs_family。
DELIVERY_POINTER = "Read this UTF-8 prompt file and follow its instructions exactly"
DELIVERY_INLINE = "You are repairing one ACL 2025 reference-extraction record"

# 指针指向的路径。7 月中途从扁平布局迁到了按年/会议分层。
POINTER_PATH = re.compile(r"(data/processed/layer4\S*?)/(agent_\w+\.md)")
PID_IN_PATH = re.compile(r"20\d\d\.acl-[a-z]+\.\d+")


def _h(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:8]


def split_blocks(sp: str) -> tuple[dict[str, str], dict[str, int]]:
    """切块，同时记下每块块体的起始字符偏移。

    偏移是这里的重点：一个块跨 run 变不变只决定「有没有分歧」，而它的偏移决定
    「分歧之前还剩多少可共享」。
    """
    body: dict[str, str] = {}
    offset: dict[str, int] = {}
    cur: list[str] = []
    name = PREAMBLE
    offset[name] = 0
    pos = 0
    for line in sp.split("\n"):
        m = BLOCK_HEAD.match(line)
        if m:
            body[name] = "\n".join(cur)
            cur = []
            name = m.group(1)
            offset[name] = pos + len(line) + 1
        else:
            cur.append(line)
        pos += len(line) + 1
    body[name] = "\n".join(cur)
    return body, offset


def classify_delivery(prompt: str) -> str:
    p = (prompt or "").lstrip()
    if p.startswith(DELIVERY_POINTER):
        return "pointer"
    if p.startswith(DELIVERY_INLINE):
        return "inline"
    return "other"


def pointer_target(prompt: str) -> tuple[str | None, str | None]:
    """指针指向的（归一化路径, 布局名）。非指针型返回 (None, None)。"""
    m = POINTER_PATH.search(prompt or "")
    if not m:
        return None, None
    norm = PID_IN_PATH.sub("<PID>", m.group(1)) + "/" + m.group(2)
    depth = norm.count("/")
    return norm, ("flat" if depth <= 4 else "nested")


def build(limit: int | None = None) -> list[dict]:
    rows = []
    for sdir in wire.session_dirs()[: limit or None]:
        s = wire.load(sdir, with_segments=False)
        sp = s.system_prompt or ""
        body, offset = split_blocks(sp)

        axis_named = set(AXIS_BLOCK.values()) | set(MACHINE_BLOCKS)
        # harness 签名 = 除去时钟/目录树/AGENTS.md/skills/机器属性之后的全部，
        # 按块名排序拼接。块名进哈希，所以块的有无也被算进去。
        harness_src = "\n\x00".join(
            f"{k}\x01{v}" for k, v in sorted(body.items()) if k not in axis_named
        )

        prompt = s.user_prompt or ""
        delivery = classify_delivery(prompt)
        ptr, layout = pointer_target(prompt)
        pid_m = PID_IN_PATH.search(prompt)

        ts_block = AXIS_BLOCK["timestamp"]
        # 时间戳块之后还剩多少字符：这些字符跨 run 本可共享，却排在时间戳之后。
        ts_off = offset.get(ts_block)
        tail = (len(sp) - ts_off) if ts_off is not None else None

        rows.append(
            {
                "sid": s.sid,
                "family": s.family,
                "created_at": s.created_at,
                "sysprompt_chars": len(sp),
                "n_blocks": len(body),
                # —— 各轴的类标签 ——
                "axis_harness": _h(harness_src),
                "axis_tree": _h(body.get(AXIS_BLOCK["tree"], "\x00")),
                "axis_agents": _h(body.get(AXIS_BLOCK["agents"], "\x00")),
                "axis_skills": _h(body.get(AXIS_BLOCK["skills"], "\x00")),
                "axis_timestamp": _h(body.get(ts_block, "\x00")),
                "axis_machine": _h(
                    "\x00".join(body.get(b, "\x01") for b in MACHINE_BLOCKS)
                ),
                # —— 时间戳的位置与它毒化的尾部 ——
                "timestamp_offset": ts_off,
                "poisoned_tail_chars": tail,
                # —— 投递形态 ——
                "delivery": delivery,
                "prompt_chars": len(prompt),
                "pointer_target": ptr,
                "pointer_layout": layout,
                "pid_year": pid_m.group(0)[:4] if pid_m else None,
                # —— 逐块明细，供 notebook 定位「第一个不同的块」——
                "block_md5": {k: _h(v) for k, v in body.items()},
                "block_chars": {k: len(v) for k, v in body.items()},
                "block_offset": offset,
                "_tree_body": body.get(AXIS_BLOCK["tree"], ""),
            }
        )
    return rows


def tree_bodies(rows) -> dict:
    """互异的目录树正文，按 axis_tree 索引。

    只有 10 份，全文存进 summary 才 16KB —— 有了它，下游才能真的 diff 出「操作者
    动了哪个目录」，而不是只看到一串哈希。
    """
    out: dict[str, str] = {}
    for r in rows:
        out.setdefault(r["axis_tree"], r["_tree_body"])
    return out


def assign_harness_versions(rows) -> dict[str, str]:
    """给 axis_harness 的每个取值一个版本号，按首次出现时间排序：V1、V2、……

    直接用哈希做标签在表里读不出先后。版本号在这里定，不在 notebook 里定 ——
    它是产物的一部分，跨 notebook / 跨脚本都得是同一套。
    """
    first: dict[str, str] = {}
    for r in rows:
        h, t = r["axis_harness"], r["created_at"] or "9999"
        if h not in first or t < first[h]:
            first[h] = t
    order = sorted(first, key=lambda h: first[h])
    return {h: f"V{i + 1}" for i, h in enumerate(order)}


def _axis_table(rows, axis) -> dict:
    c = Counter(r[axis] for r in rows)
    return {"n_distinct": len(c), "sizes": sorted(c.values(), reverse=True)}


def summarize(rows) -> dict:
    axes = ["axis_harness", "axis_tree", "axis_agents", "axis_skills",
            "axis_timestamp", "axis_machine"]
    out = {"n_sessions": len(rows), "axes": {a: _axis_table(rows, a) for a in axes}}

    # harness 版本：号、哈希、份数、起止日期
    vers: dict[str, dict] = {}
    for r in rows:
        v = r.get("harness_version")
        if v is None:
            continue
        d = vers.setdefault(v, {"axis_harness": r["axis_harness"], "n": 0,
                                "first": None, "last": None})
        d["n"] += 1
        day = (r["created_at"] or "")[:10]
        if day:
            d["first"] = day if d["first"] is None else min(d["first"], day)
            d["last"] = day if d["last"] is None else max(d["last"], day)
    out["harness_versions"] = dict(sorted(vers.items()))

    # 联合类（不含时间戳）：跨 run 前缀能不能对齐，由这四轴决定。
    joint = Counter(
        (r["axis_harness"], r["axis_agents"], r["axis_skills"], r["axis_tree"])
        for r in rows
    )
    out["joint_classes"] = {
        "n": len(joint),
        "rows": [
            {"harness": k[0], "agents": k[1], "skills": k[2], "tree": k[3], "n": v}
            for k, v in joint.most_common()
        ],
    }

    # s0 的 sysprompt_chars 与联合类是不是双射？是的话 s0 早就有精确类标签，
    # 下游不必重扫语料。这条必须由脚本判定，不能让 notebook 断言。
    by_len = defaultdict(set)
    by_cls = defaultdict(set)
    for r in rows:
        k = (r["axis_harness"], r["axis_agents"], r["axis_skills"], r["axis_tree"])
        by_len[r["sysprompt_chars"]].add(k)
        by_cls[k].add(r["sysprompt_chars"])
    out["sysprompt_chars_is_class_label"] = {
        "bijective": all(len(v) == 1 for v in by_len.values())
        and all(len(v) == 1 for v in by_cls.values()),
        "n_lengths": len(by_len),
        "n_classes": len(by_cls),
        "lengths_mapping_to_multiple_classes": {
            k: len(v) for k, v in by_len.items() if len(v) > 1
        },
    }

    # 时间戳之后那些跨 run 本可共享、却无法复用的字符。
    tails = sorted(r["poisoned_tail_chars"] for r in rows
                   if r["poisoned_tail_chars"] is not None)
    offs = sorted(r["timestamp_offset"] for r in rows if r["timestamp_offset"] is not None)
    if tails:
        out["timestamp_poisoning"] = {
            "n_with_timestamp_block": len(tails),
            "timestamp_offset": {"min": offs[0], "p50": offs[len(offs) // 2],
                             "max": offs[-1]},
            "poisoned_tail_chars": {"min": tails[0], "p50": tails[len(tails) // 2],
                                    "max": tails[-1],
                                    "sum": sum(tails)},
            "note": "时间戳块位于 systemPrompt 中部。其后的目录树 / AGENTS.md / "
                    "skills 清单 / Ultimate Reminders 跨 run 逐字稳定，却因排在"
                    "时间戳之后而无法复用。把时间戳移到 systemPrompt 末尾即可回收，"
                    "语义不变。",
        }

    # 各轴的时间跨度：类是不是按时间连续排布的。
    span = defaultdict(list)
    for r in rows:
        if r["created_at"]:
            span[r["axis_tree"]].append(r["created_at"][:10])
    out["tree_time_spans"] = {
        k: {"n": len(v), "first": min(v), "last": max(v), "n_days": len(set(v))}
        for k, v in sorted(span.items(), key=lambda x: -len(x[1]))
    }

    # 投递形态。与 family 的交叉表用来显示 family 这个标签编码了两件事。
    out["delivery"] = dict(Counter(r["delivery"] for r in rows))
    out["delivery_vs_family"] = {
        f"{d}/{f}": n for (d, f), n in
        Counter((r["delivery"], r["family"]) for r in rows).most_common()
    }
    plen = defaultdict(list)
    for r in rows:
        plen[r["delivery"]].append(r["prompt_chars"])
    out["prompt_chars_by_delivery"] = {
        d: {"n": len(v), "min": min(v), "p50": sorted(v)[len(v) // 2],
            "max": max(v)}
        for d, v in plen.items()
    }
    out["pointer_layout"] = dict(Counter(
        r["pointer_layout"] for r in rows if r["pointer_layout"]))
    out["pointer_target"] = dict(Counter(
        r["pointer_target"] for r in rows if r["pointer_target"]).most_common(10))
    out["pid_year"] = dict(Counter(r["pid_year"] for r in rows if r["pid_year"]))
    out["tree_bodies"] = tree_bodies(rows)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="只扫前 N 份，用于冒烟测试")
    args = ap.parse_args()

    rows = build(limit=args.limit)
    ver = assign_harness_versions(rows)
    for r in rows:
        r["harness_version"] = ver[r["axis_harness"]]
    hdr = provenance.header(SCRIPT, {"limit": args.limit})
    summ = summarize(rows)
    # 目录树正文只进 summary 的 tree_bodies（互异 10 份），不逐 session 落盘
    for r in rows:
        r.pop("_tree_body", None)
    path = provenance.write_jsonl("s0b_prompt_blocks.jsonl", hdr, rows)
    provenance.write_json("s0b_summary.json", hdr, summ)

    print(f"[s0b] 拆解 {len(rows)} 份 session 的 systemPrompt → {path}")
    for a, d in summ["axes"].items():
        print(f"       {a:16} 互异 {d['n_distinct']:>5}  最大类 {d['sizes'][0]}")
    for v, d in summ["harness_versions"].items():
        print(f"       harness {v}  {d['n']:>5} 份  {d['first']} .. {d['last']}")
    print(f"[s0b] 四轴联合（不含时间戳）: {summ['joint_classes']['n']} 类")
    b = summ["sysprompt_chars_is_class_label"]
    print(f"[s0b] sysprompt_chars 与联合类双射: {b['bijective']} "
          f"（{b['n_lengths']} 个长度 / {b['n_classes']} 个类）")
    cp = summ.get("timestamp_poisoning")
    if cp:
        print(f"[s0b] 时间戳位于 systemPrompt 第 {cp['timestamp_offset']['p50']} 字符（p50），"
              f"其后 {cp['poisoned_tail_chars']['p50']} 字符无法复用")
    print(f"[s0b] 投递形态: {summ['delivery']}")


if __name__ == "__main__":
    main()
