"""把 MinerU 服务返回的逐页 block 装配成可用产出（纯函数，不碰网络、不碰磁盘）。

为什么需要这一层：`mineru_vl_utils` 只把 block 的 `content` 拼成 Markdown
（`post_process/json2markdown.py`，全文三十行），丢掉 type、bbox、页号，并且：

- `image_block` 容器与它内部的子图**平级**出现，逐块裁图会把一张逻辑图切成碎片；
- `image_caption` / `table_caption` 是独立块，与图表只是顺序相邻，没有归属关系；
- `header` / `footer` / `page_number` 等版面附属物留在正文流里；
- `title` 不带 `#`，正文没有章节结构；
- 行内公式是 `\\(...\\)`，而形如 `\\[2\\]` 的引用编号也被包成了公式。

以上都由官方 `mineru` 包在 block → middle_json → md/content_list 这条链上处理。
我们不装 `mineru`（它的 extras 与主线的 vLLM 版本冲突，见根 pyproject），所以把其中
与 block 结构有关的几段**移植**过来。每处都标了参照位置，便于对照上游改动：

    references/repos/MinerU @ 3.4.0
      mineru/utils/visual_magic_model_utils.py   absorb_image_block_members / regroup_visual_blocks
      mineru/backend/vlm/vlm_magic_model.py      类型映射、discarded 分流、行内公式切分
      mineru/backend/vlm/vlm_middle_json_mkcontent.py  md 与 content_list 的生成

**有意简化的地方**（上游有、这里没有）：

1. caption 归属只保留"阅读顺序相邻 + 边距最近"这条主干，去掉了上游
   `is_block_outside_visual_gap` 的几何豁免。代价是跨栏摆放的 caption 可能匹配不上——
   宁可 `captions` 为空，也不要错配到别的图上。
2. 上游 `merge_para_with_text` 的西文连字符断行、CJK 空格处理依赖逐行 span；服务返回的
   是整段 content（一个 span），无从施加。段落合并沿用服务给的 `merge_prev`。
3. 不做 LLM 辅助的标题分级（上游默认也关），`title` 一律 `#`，与上游 `get_title_level`
   的默认值一致。层级留给下游按编号自己判断。
4. 不做跨页表格合并。要的话开客户端的 `enable_cross_page_table_merge`，别在这里补。
5. `code` / `algorithm` 只渲染成围栏代码块，不走上游的 HTML 渲染。
"""

from __future__ import annotations

import math
import re

# ---------------------------------------------------------------- 类型常量
# 参照 vlm_magic_model.py 的类型映射：服务返回的 raw type → 我们的装配语义。
VISUAL_BODY_TYPES = ("image", "chart", "table")     # 视觉主体
CONTAINER_TYPE = "image_block"                      # 多图容器（Fig.7 那种由子图拼成的图）
CAPTION_TYPES = ("image_caption", "table_caption", "code_caption", "caption")
FOOTNOTE_TYPES = ("image_footnote", "table_footnote", "footnote")
# 版面附属物：分流到 discarded，不进正文。参照 vlm_magic_model.py 的 discarded_blocks 分支。
DISCARDED_TYPES = ("header", "footer", "page_number", "aside_text", "page_footnote")
CODE_TYPES = ("code", "algorithm")
# 结构性空容器：内容在别的块里，自身不产出正文。
STRUCTURAL_TYPES = ("equation_block", "list")

INLINE_MATH = ("$", "$")
DISPLAY_MATH = ("$$", "$$")

# 吸收子图的重叠阈值，与上游 absorb_image_block_members 的 0.9 一致。
ABSORB_OVERLAP = 0.9
# 平局时的边距容差。上游用像素（> 2px），我们在归一化坐标里比较，按 A4 文字区约
# 600pt 折算，2pt ≈ 0.003。
EDGE_TOLERANCE = 0.003


# ---------------------------------------------------------------- 几何
def overlap_ratio_in_first(bbox1: list[float], bbox2: list[float]) -> float:
    """bbox1 与 bbox2 的交集占 bbox1 的比例。boxbase.calculate_overlap_area_in_bbox1_area_ratio"""
    x_left = max(bbox1[0], bbox2[0])
    y_top = max(bbox1[1], bbox2[1])
    x_right = min(bbox1[2], bbox2[2])
    y_bottom = min(bbox1[3], bbox2[3])
    if x_right < x_left or y_bottom < y_top:
        return 0.0
    inter = (x_right - x_left) * (y_bottom - y_top)
    area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    return inter / area if area else 0.0


def bbox_area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def bbox_gap_distance(a: list[float], b: list[float]) -> float:
    """两框之间的边距（相离时为间隙，相交时为 0）。boxbase.bbox_distance 的等价简写。"""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def bbox_center_distance(a: list[float], b: list[float]) -> float:
    ax, ay = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bx, by = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return math.hypot(ax - bx, ay - by)


def relative_bbox(child: list[float], parent: list[float]) -> list[float]:
    """子图在容器内的相对位置。visual_magic_model_utils.relative_bbox

    上游在像素坐标下用 `max(w, 1)` 防退化；这里是归一化坐标，改成防零除。
    """
    px0, py0, px1, py1 = parent
    pw = (px1 - px0) or 1.0
    ph = (py1 - py0) or 1.0
    return [
        round(min(max((child[0] - px0) / pw, 0.0), 1.0), 3),
        round(min(max((child[1] - py0) / ph, 0.0), 1.0), 3),
        round(min(max((child[2] - px0) / pw, 0.0), 1.0), 3),
        round(min(max((child[3] - py0) / ph, 0.0), 1.0), 3),
    ]


# ---------------------------------------------------------------- 内容清洗
def clean_bracket_escapes(content: str | None) -> str | None:
    """把成对的 `\\[...\\]` 还原成 `[...]`。visual_magic_model_utils.clean_content

    模型会把引用编号写成 `\\[2\\]`（当成了公式）。不还原的话，正文里的
    `\\( [2] \\) – \\( [4] \\)` 这类片段会让引用抽取无从下手。
    """
    if not content:
        return content
    if content.count("\\[") and content.count("\\[") == content.count("\\]"):
        return re.sub(r"\\\[(.*?)\\\]", lambda m: f"[{m.group(1)}]", content)
    return content


def inline_math_to_dollar(content: str) -> str:
    """`\\(x\\)` → `$x$`。参照 vlm_magic_model.py 把行内公式切成 span、再由
    mkcontent 用 delimiters 包起来的两步；我们只换分隔符，语义相同。
    """
    left, right = INLINE_MATH
    return re.sub(
        r"\\\((.+?)\\\)",
        lambda m: f"{left}{m.group(1).strip()}{right}",
        content,
        flags=re.DOTALL,
    )


def display_math_to_dollar(content: str) -> str:
    """独立公式 `\\[ ... \\]` → `$$ ... $$`。上游 isolated_formula_clean + display delimiters。"""
    text = content.strip()
    if text.startswith("\\[") and text.endswith("\\]"):
        text = text[2:-2].strip()
    left, right = DISPLAY_MATH
    return f"{left}\n{text}\n{right}"


def normalize_text(content: str | None) -> str:
    if not content:
        return ""
    return inline_math_to_dollar(clean_bracket_escapes(content) or "")


# ---------------------------------------------------------------- 装配
class VisualGroup(dict):
    """一个视觉主体及其 caption/footnote。对应上游的 two_layer_block。

    键：type / bbox / index / sub_type / content / sub_images / captions / footnotes
    """


def _absorb_container_members(blocks: list[dict]) -> tuple[set[int], dict[int, list[dict]]]:
    """容器吸收子图：重叠占子图面积 ≥ 0.9 即归属该容器。

    visual_magic_model_utils.absorb_image_block_members。返回 (被吸收的块序号,
    容器序号 → 子图相对位置列表)。被吸收的子图不再单独裁图、不再进正文 —— 这是
    "一张 Fig.7 被切成十一张碎片"的修法。
    """
    containers = [(i, b) for i, b in enumerate(blocks) if b.get("type") == CONTAINER_TYPE]
    members = [(i, b) for i, b in enumerate(blocks) if b.get("type") in ("image", "chart")]
    if not containers or not members:
        return set(), {}

    assignment: dict[int, int] = {}
    for mi, member in members:
        best_key = None
        best_parent = None
        for ci, container in containers:
            ratio = overlap_ratio_in_first(member["bbox"], container["bbox"])
            if ratio < ABSORB_OVERLAP:
                continue
            # 上游的择优键：重叠比大的优先，其次容器面积小的、序号小的。
            key = (-ratio, bbox_area(container["bbox"]), ci)
            if best_key is None or key < best_key:
                best_key, best_parent = key, ci
        if best_parent is not None:
            assignment[mi] = best_parent

    absorbed: set[int] = set()
    sub_images: dict[int, list[dict]] = {}
    for ci, container in containers:
        owned = sorted(mi for mi, parent in assignment.items() if parent == ci)
        if not owned:
            continue
        absorbed.update(owned)
        sub_images[ci] = [
            {
                "type": blocks[mi].get("type"),
                "block": mi,
                "bbox_in_parent": relative_bbox(blocks[mi]["bbox"], container["bbox"]),
            }
            for mi in owned
        ]
    return absorbed, sub_images


def _effective_index_diff(child_i: int, main_i: int, seq: list[int], pos: dict[int, int],
                          kinds: dict[int, str], child_kind: str) -> int:
    """阅读顺序距离，同类子块视为零成本。visual_magic_model_utils.effective_visual_index_diff

    距离在**有效块序列**上算（被容器吸收的子图已剔除），否则一张多图容器的 caption
    会因为中间隔着一堆子图而离自己的容器"很远"。
    """
    lo, hi = min(pos[child_i], pos[main_i]), max(pos[child_i], pos[main_i])
    skipped = sum(1 for i in seq[lo + 1:hi] if kinds.get(i) == child_kind)
    return hi - lo - skipped


def _is_neighbor(child_i: int, main_i: int, seq: list[int], pos: dict[int, int],
                 kinds: dict[int, str], child_kind: str) -> bool:
    """两者之间是否没有夹着别的东西。visual_magic_model_utils.is_visual_neighbor

    同样在有效块序列上扫描（上游的 `effective_blocks` / `visual_relation_blocks`）。
    简化处：不实现上游 `is_block_outside_visual_gap` 的几何豁免（见模块 docstring）。
    """
    if child_kind == "footnote" and pos[child_i] < pos[main_i]:
        return False  # 脚注不可能在主体之前
    allowed = {"caption"} if child_kind == "caption" else {"caption", "footnote"}
    lo, hi = min(pos[child_i], pos[main_i]), max(pos[child_i], pos[main_i])
    for i in seq[lo + 1:hi]:
        if kinds.get(i) in allowed:
            continue
        return False
    return True


def _find_parent(child_i: int, child: dict, mains: list[tuple[int, dict]], seq: list[int],
                 pos: dict[int, int], kinds: dict[int, str], child_kind: str) -> int | None:
    """为 caption/footnote 找归属主体。visual_magic_model_utils.find_best_visual_parent"""
    candidates = [(i, b) for i, b in mains if _is_neighbor(child_i, i, seq, pos, kinds, child_kind)]
    if not candidates:
        return None

    diffs = {i: _effective_index_diff(child_i, i, seq, pos, kinds, child_kind) for i, _ in candidates}
    best_diff = min(diffs.values())
    closest = [(i, b) for i, b in candidates if diffs[i] == best_diff]
    if len(closest) == 1:
        return closest[0][0]

    edges = [(i, bbox_gap_distance(child["bbox"], b["bbox"])) for i, b in closest]
    values = [d for _, d in edges]
    if max(values) - min(values) > EDGE_TOLERANCE:
        return min(edges, key=lambda item: (item[1], item[0]))[0]

    # 上游的平局规则：表格 caption 夹在两表之间时归后一个，脚注归前一个。
    if child_kind == "caption" and all(b.get("type") == "table" for _, b in closest):
        return max(i for i, _ in closest)
    if child_kind == "footnote":
        return min(i for i, _ in closest)
    return min(closest, key=lambda item: (bbox_center_distance(child["bbox"], item[1]["bbox"]), item[0]))[0]


def _kind_of(block: dict) -> str:
    btype = block.get("type")
    if btype in CAPTION_TYPES:
        return "caption"
    if btype in FOOTNOTE_TYPES:
        return "footnote"
    if btype in DISCARDED_TYPES:
        return "discarded"
    # code / algorithm 也是"主体 + caption"的结构（上游 VISUAL_MAIN_TYPES 含 CODE_BODY），
    # 只是不截图：它的内容本来就是文本。
    if btype == CONTAINER_TYPE or btype in VISUAL_BODY_TYPES or btype in CODE_TYPES:
        return "visual"
    if btype in STRUCTURAL_TYPES:
        return "structural"
    return "flow"


def assemble_page(blocks: list[dict], page_no: int) -> dict:
    """把一页的 raw block 装配成 {items, discarded}。

    `items` 按阅读顺序排列，每项是：
      - `{"kind": "visual", ...VisualGroup}`  视觉主体（含 captions/footnotes/sub_images）
      - `{"kind": "flow", "block": idx, "type": ..., "content": ...}`  正文类块
    `discarded` 是页眉页脚一类，保留但不进正文。
    """
    kinds = {i: _kind_of(b) for i, b in enumerate(blocks)}
    absorbed, sub_images = _absorb_container_members(blocks)

    # 有效块序列：剔掉被容器吸收的子图。上游 regroup_visual_blocks 的 effective_blocks，
    # caption 归属的邻接与距离都在这个序列上算。
    effective_seq = [i for i in range(len(blocks)) if i not in absorbed]
    effective_pos = {i: k for k, i in enumerate(effective_seq)}

    # 被容器吸收的子图退出阅读流；容器自己成为主体。
    mains = [
        (i, b) for i, b in enumerate(blocks)
        if i not in absorbed and kinds[i] == "visual"
    ]
    main_indices = {i for i, _ in mains}

    children: dict[int, dict[str, list[int]]] = {i: {"captions": [], "footnotes": []} for i, _ in mains}
    orphans: list[int] = []
    for i, block in enumerate(blocks):
        kind = kinds[i]
        if kind not in ("caption", "footnote"):
            continue
        parent = _find_parent(i, block, mains, effective_seq, effective_pos, kinds, kind)
        if parent is None:
            orphans.append(i)      # 配不上就当普通段落，不硬塞给某张图
            continue
        children[parent]["captions" if kind == "caption" else "footnotes"].append(i)

    consumed = set(absorbed)
    for i in children:
        consumed.update(children[i]["captions"])
        consumed.update(children[i]["footnotes"])

    items: list[dict] = []
    discarded: list[dict] = []
    for i, block in enumerate(blocks):
        btype = block.get("type")
        if i in consumed:
            continue
        if kinds[i] == "discarded":
            discarded.append({"block": i, "type": btype, "bbox": block["bbox"],
                              "content": normalize_text(block.get("content"))})
            continue
        if i in main_indices:
            # 容器本身没有 content；子图的描述（若有）也随子图一起被吸收掉了。
            if btype == CONTAINER_TYPE:
                group_type, sub_type = "image", block.get("sub_type")
            elif btype in CODE_TYPES:
                group_type, sub_type = "code", btype
            else:
                group_type, sub_type = btype, block.get("sub_type")
            group = VisualGroup(
                kind="visual",
                block=i,
                type=group_type,
                is_container=btype == CONTAINER_TYPE,
                bbox=block["bbox"],
                angle=block.get("angle"),
                sub_type=sub_type,
                content=block.get("content") or "",
                sub_images=sub_images.get(i, []),
                captions=[{"block": c, "text": normalize_text(blocks[c].get("content"))}
                          for c in children[i]["captions"]],
                footnotes=[{"block": c, "text": normalize_text(blocks[c].get("content"))}
                           for c in children[i]["footnotes"]],
            )
            items.append(group)
            continue
        if kinds[i] == "structural":
            continue           # equation_block / 空 list 容器：内容在别的块里
        items.append({"kind": "flow", "block": i, "type": btype,
                      "bbox": block["bbox"],
                      "merge_prev": bool(block.get("merge_prev")),
                      "content": block.get("content") or "",
                      "orphan_child": i in orphans})
    return {"page": page_no, "items": items, "discarded": discarded}


def assemble(pages_blocks: list[list[dict]]) -> list[dict]:
    return [assemble_page(blocks, i) for i, blocks in enumerate(pages_blocks, start=1)]


# ---------------------------------------------------------------- 裁图计划
def crop_plan(pages: list[dict]) -> list[dict]:
    """要裁哪些图：每个视觉主体一张（容器裁整图，不裁子图）。

    上游把 image/table/chart/interline_equation 的 span 都截图
    （model_output_to_middle_json.blocks_to_page_info）。我们不截公式：公式有 LaTeX，
    截图对后续用处不大，需要时按 blocks.json 里的 bbox 补裁。
    """
    plan = []
    for page in pages:
        for item in page["items"]:
            if item.get("kind") != "visual" or item["type"] not in VISUAL_BODY_TYPES:
                continue    # code 组不截图：内容本身是文本
            plan.append({
                "page": page["page"],
                "block": item["block"],
                "type": item["type"],
                "bbox": item["bbox"],
                "angle": item.get("angle"),
                "name": f"p{page['page']:03d}-b{item['block']:02d}-{item['type']}.png",
            })
    return plan


# ---------------------------------------------------------------- Markdown
def _visual_details(content: str, vtype: str, sub_type: str | None) -> str:
    """把模型"读图"得到的结构化内容包进 <details>。

    照抄上游 mkcontent._build_visual_details_block 的形态：折叠起来，既不干扰阅读，
    又明确标出这段不是从文字里抽的，而是模型看图写的。
    """
    if not content.strip():
        return ""
    summary = sub_type or ("chart content" if vtype == "chart" else "image content")
    return f"<details>\n<summary>{summary}</summary>\n\n{content}\n</details>"


def _visual_markdown(item: dict, crop_paths: dict[tuple[int, int], str], table_html: bool = True) -> str:
    """一个视觉主体的 md。

    主体与它的 caption / footnote 按**原始 block 序号**混排，参照上游
    mkcontent._merge_visual_blocks_to_markdown → _get_blocks_in_index_order：
    表格标题通常在表前、图的说明通常在图后，顺序由版面决定，不该由我们钉死。
    """
    body_parts: list[str] = []

    rel = crop_paths.get((item["page"], item["block"]))
    if item["type"] == "code":
        body = item["content"].strip()
        if body:
            body_parts.append(body if body.startswith("```") else f"```\n{body}\n```")
    elif item["type"] == "table":
        # 上游：有 HTML 就用 HTML，没有才退回图片。裁图另用注释指路，便于回查。
        if table_html and item["content"].strip():
            body_parts.append(item["content"].strip())
            if rel:
                body_parts.append(f"<!-- crop: {rel} -->")
        elif rel:
            body_parts.append(f"![]({rel})")
    else:
        if rel:
            body_parts.append(f"![]({rel})")
        details = _visual_details(item["content"], item["type"], item.get("sub_type"))
        if details:
            body_parts.append(details)

    segments: list[tuple[int, str]] = [(item["block"], "\n\n".join(body_parts))]
    for child in [*item["captions"], *item["footnotes"]]:
        if child["text"].strip():
            segments.append((child["block"], child["text"]))
    segments.sort(key=lambda seg: seg[0])
    return "\n\n".join(text for _, text in segments if text.strip())


def _flow_markdown(item: dict) -> str:
    btype = item["type"]
    content = item["content"]
    if not content.strip():
        return ""
    if btype == "equation":
        return display_math_to_dollar(clean_bracket_escapes(content) or content)
    if btype in CODE_TYPES:
        body = content.strip()
        if body.startswith("```"):
            return body
        return f"```\n{body}\n```"
    text = normalize_text(content)
    if btype in ("title", "doc_title", "paragraph_title"):
        # 上游 get_title_level 默认 level=1，未开 LLM 分级时所有标题都是 `#`。
        return f"# {re.sub(r"\s+", " ", text).strip()}"
    return text


def to_markdown(pages: list[dict], crop_paths: dict[tuple[int, int], str],
                table_html: bool = True) -> str:
    """装配结果 → Markdown。版面附属物不进正文（上游 discarded_blocks 同理）。"""
    chunks: list[str] = []
    for page in pages:
        for item in page["items"]:
            if item.get("kind") == "visual":
                item = {**item, "page": page["page"]}
                text = _visual_markdown(item, crop_paths, table_html=table_html)
            else:
                text = _flow_markdown(item)
            if not text.strip():
                continue
            # 服务标了 merge_prev 的文本块是上一段的续写（跨栏/跨页），拼回同一段。
            if item.get("kind") == "flow" and item.get("merge_prev") and chunks:
                joiner = "" if re.search(r"[一-鿿]", text) else " "
                chunks[-1] = chunks[-1] + joiner + text
            else:
                chunks.append(text)
    return "\n\n".join(chunks) + "\n"


# ---------------------------------------------------------------- content_list
def to_content_list(pages: list[dict], crop_paths: dict[tuple[int, int], str]) -> list[dict]:
    """官方 content_list.json 形态的扁平清单。

    参照 mkcontent.make_blocks_to_content_list：视觉主体给 img_path / content /
    *_caption / *_footnote / sub_type，标题给 text + text_level，公式给 text_format。
    差异：bbox 我们直接给归一化的 [0,1] 浮点（上游是 0-1000 整数），因为服务返回的就是
    归一化坐标，转成千分比只会引入一次取整误差。
    """
    out: list[dict] = []
    for page in pages:
        page_idx = page["page"] - 1
        for item in page["items"]:
            if item.get("kind") == "visual":
                vtype = item["type"]
                rel = crop_paths.get((page["page"], item["block"]))
                entry = {
                    "type": vtype,
                    "img_path": rel or "",
                    "bbox": [round(v, 4) for v in item["bbox"]],
                    "page_idx": page_idx,
                    f"{vtype}_caption": [c["text"] for c in item["captions"]],
                    f"{vtype}_footnote": [f["text"] for f in item["footnotes"]],
                }
                if vtype == "table":
                    entry["table_body"] = item["content"]
                elif vtype == "code":
                    entry["code_body"] = item["content"]
                    entry.pop("img_path", None)
                else:
                    entry["content"] = item["content"]
                if item.get("sub_type"):
                    entry["sub_type"] = item["sub_type"]
                if item.get("sub_images"):
                    entry["sub_images"] = item["sub_images"]
                out.append(entry)
                continue

            btype = item["type"]
            if not item["content"].strip():
                continue
            if btype in ("title", "doc_title", "paragraph_title"):
                out.append({"type": "text", "text": normalize_text(item["content"]),
                            "text_level": 1, "bbox": [round(v, 4) for v in item["bbox"]],
                            "page_idx": page_idx})
            elif btype == "equation":
                out.append({"type": "equation",
                            "text": display_math_to_dollar(item["content"]),
                            "text_format": "latex",
                            "bbox": [round(v, 4) for v in item["bbox"]],
                            "page_idx": page_idx})
            else:
                out.append({"type": btype, "text": normalize_text(item["content"]),
                            "bbox": [round(v, 4) for v in item["bbox"]],
                            "page_idx": page_idx})
    return out


def counts(pages: list[dict]) -> dict:
    """装配结果的计数，进 meta.json 便于一眼看出这一篇抽到了什么。"""
    visual: dict[str, int] = {}
    flow: dict[str, int] = {}
    captioned = 0
    visual_total = 0
    containers = 0
    for page in pages:
        for item in page["items"]:
            if item.get("kind") == "visual":
                visual_total += 1
                visual[item["type"]] = visual.get(item["type"], 0) + 1
                captioned += bool(item["captions"])
                containers += bool(item.get("is_container"))
            else:
                flow[item["type"]] = flow.get(item["type"], 0) + 1
    return {
        "visual": visual,
        "visual_total": visual_total,
        "visual_containers": containers,
        "visual_with_caption": captioned,
        "flow": dict(sorted(flow.items())),
        "discarded": sum(len(p["discarded"]) for p in pages),
    }
