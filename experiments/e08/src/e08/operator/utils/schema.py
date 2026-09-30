"""graph_model.md 的机器可读约束：写入前的结构检查依据。

只检查结构（Label、属性、取值、关系端点、anchor 是否齐全），不检查内容是否忠实于原文。
与 graph_model.md 不一致时以文档为准，改这里。`id` 与 `embedding`、`_batch` 等派生属性由系统写入，不在此列。
"""

from .anchor import check_anchor

RESOURCE_KINDS = {"Dataset", "Benchmark", "Model", "CodeRepo", "Tool"}   # Resource 恰好带其中一个次级 Label

# 节点：主 Label -> (必填属性, 可选属性)。所有节点另可带 note。
NODES = {
    "Paper": ({"title"}, {"aliases", "year", "s2_id", "arxiv_id", "paper_type", "description", "markdown_path", "anchor"}),
    "Contribution": ({"text", "anchor"}, set()),
    "Method": ({"name", "description"}, {"aliases", "anchor"}),
    "MethodConcept": ({"name", "description"}, {"aliases"}),
    "Task": ({"name", "description"}, {"aliases"}),
    "Claim": ({"text", "anchor"}, set()),
    "ClaimConcept": ({"text"}, set()),
    "Issue": ({"text"}, {"description"}),
    "Resource": ({"name", "description"}, {"aliases", "url"}),
    "ResourceRecord": ({"description", "anchor"}, {"url"}),
    "Experiment": ({"description", "anchor"}, set()),
    "Metric": ({"name", "description"}, {"aliases", "anchor"}),
    "Observation": ({"kind", "description", "observed_at", "target", "evidence"}, set()),
}
LIST_PROPS = {"aliases", "anchor", "evidence"}
NODE_ENUMS = {
    ("Paper", "paper_type"): {"method", "dataset", "benchmark", "empirical", "survey", "other"},
    ("Observation", "kind"): {"repo_inspection", "execution", "reproduction"},
}


def _rel(ends, anchor="optional", enums=None, required=(), symmetric=False):
    """ends: [(起点主 Label, 终点主 Label)]；anchor: required / optional；enums: {属性: 取值}；required: 必填属性。"""
    return {"ends": ends, "anchor": anchor, "enums": enums or {}, "required": set(required), "symmetric": symmetric}


# 关系：Type -> 约束。所有关系可带 description 与 anchor。
RELS = {
    # 论文、贡献与具体内容
    "HAS_CONTRIBUTION": _rel([("Paper", "Contribution")]),
    "HAS_CLAIM": _rel([("Paper", "Claim"), ("Contribution", "Claim")]),
    "ABOUT": _rel([("Contribution", t) for t in ("Method", "Resource", "Experiment")]
                  + [("Claim", t) for t in ("Method", "MethodConcept", "Task", "Resource", "Metric")]
                  + [("Issue", t) for t in ("Task", "MethodConcept", "Method")]),
    "EXPRESSES": _rel([("Claim", "ClaimConcept")]),
    # 任务与问题
    "ADDRESSES": _rel([("Method", "Task")], anchor="required"),
    "ON_TASK": _rel([("Experiment", "Task")]),
    "FOR_TASK": _rel([("Resource", "Task")]),
    "RAISES": _rel([("Paper", "Issue")], anchor="required"),
    "RESPONDS_TO": _rel([("Claim", "Issue")], anchor="required", enums={"stance": {"yes", "no", "partial", "reframes"}}),
    # 论文与方法
    "HAS_METHOD": _rel([("Paper", "Method")], anchor="required", required=["role"],
                       enums={"role": {"proposed", "reused", "extended", "compared"}}),
    "DERIVED_FROM": _rel([("Method", "Method"), ("Method", "Resource"), ("Resource", "Resource")]),
    "PRODUCES": _rel([("Method", "Resource")]),
    "INSTANCE_OF": _rel([("Method", "MethodConcept")]),
    # 论文与资源经验
    "HAS_RESOURCE_RECORD": _rel([("Paper", "ResourceRecord")]),
    "DESCRIBES": _rel([("ResourceRecord", "Resource")]),
    "HAS_METRIC": _rel([("ResourceRecord", "Metric")]),
    "RELATES_TO": _rel([("Paper", "Resource")], anchor="required", required=["role"],
                       enums={"role": {"introduced", "used", "evaluated", "cited_only"}}),
    # 实验与依据
    "REPORTS": _rel([("Paper", "Experiment")]),
    "SUPPORTED_BY": _rel([("Claim", "Experiment")]),
    "MEASURED_BY": _rel([("Experiment", "Metric")]),
    "EVALUATES": _rel([("Experiment", "Method"), ("Experiment", "Resource")], required=["role"],
                      enums={"role": {"target", "baseline"}}),
    "USES": _rel([("Experiment", "Resource")], required=["role"],
                 enums={"role": {"training_data", "evaluation_data", "analysis_input", "tooling"}}),
    # 第一手检查
    "OBSERVES": _rel([("Observation", "Resource")]),
    "CHECKS": _rel([("Observation", "ResourceRecord"), ("Observation", "Claim")], required=["verdict"],
                   enums={"verdict": {"consistent", "inconsistent", "partial", "inconclusive"}}),
    # 论文互相参照；只有参考文献条目时可以没有 anchor
    "CITES": _rel([("Paper", "Paper")]),
    # 同类 Node 之间
    "USES_COMPONENT": _rel([("Method", "Method")]),
    "DIFFERS_FROM": _rel([("Method", "Method")], symmetric=True),
    "SUBTYPE_OF": _rel([("MethodConcept", "MethodConcept"), ("Task", "Task")]),
    "OVERLAPS_WITH": _rel([("MethodConcept", "MethodConcept")], symmetric=True),
    "SUPPORTS": _rel([("Claim", "Claim")]),
    "CHALLENGES": _rel([("Claim", "Claim")]),
    "QUALIFIES": _rel([("Claim", "Claim")]),
    "REFINES": _rel([("ClaimConcept", "ClaimConcept"), ("Issue", "Issue")]),
    "IMPLIES": _rel([("ClaimConcept", "ClaimConcept")]),
    "CONTRADICTS": _rel([("ClaimConcept", "ClaimConcept")], symmetric=True),
    "PART_OF": _rel([("Resource", "Resource")]),
    "EXTENDS": _rel([("Contribution", "Contribution")]),
    # Agent 扩展关系：端点不限，kind 给出关系名称
    "RELATED_TO": _rel(None, required=["kind", "description"]),
}
SYMMETRIC = {t for t, r in RELS.items() if r["symmetric"]}
REL_PROPS = {"description", "anchor", "role", "stance", "verdict", "kind"}


def _check_anchors(value, where) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"{where}: anchor 应为非空列表"]
    return [f"{where}: {e}" for a in value for e in check_anchor(a)]


def check_node(labels: list[str], props: dict, where="node") -> list[str]:
    """新建节点的结构检查；返回错误列表，空表示通过。"""
    if not labels or labels[0] not in NODES:
        return [f"{where}: 主 Label {labels[:1]} 不在 graph_model 中"]
    main = labels[0]
    errors = []
    extra_labels = set(labels[1:])
    if main == "Resource":
        if len(extra_labels) != 1 or not extra_labels <= RESOURCE_KINDS:
            errors.append(f"{where}: Resource 需要恰好一个次级 Label（{'/'.join(sorted(RESOURCE_KINDS))}），得到 {labels[1:]}")
    elif extra_labels:
        errors.append(f"{where}: {main} 不带次级 Label，得到 {labels[1:]}")
    required, optional = NODES[main]
    given = {k for k, v in props.items() if v not in (None, "", [])}
    if missing := required - given:
        errors.append(f"{where}: 缺少必填属性 {sorted(missing)}")
    if unknown := set(props) - required - optional - {"note"}:
        errors.append(f"{where}: {main} 没有属性 {sorted(unknown)}")
    for k in LIST_PROPS & given:
        if not isinstance(props[k], list) or not all(isinstance(x, str) for x in props[k]):
            errors.append(f"{where}: {k} 应为字符串列表")
    for (label, k), allowed in NODE_ENUMS.items():
        if label == main and k in given and props[k] not in allowed:
            errors.append(f"{where}: {k}={props[k]!r} 不在 {sorted(allowed)} 中")
    if "anchor" in given:
        errors += _check_anchors(props["anchor"], where)
    return errors


def check_rel(rel_type: str, from_labels: list[str], to_labels: list[str], props: dict, where="relationship") -> list[str]:
    """关系的结构检查：类型、端点主 Label 与方向、属性与取值、anchor。"""
    if rel_type not in RELS:
        return [f"{where}: 关系类型 {rel_type} 不在 graph_model 中；新语义用 RELATED_TO + kind"]
    rule = RELS[rel_type]
    errors = []
    ends = (from_labels[0], to_labels[0])
    if rule["ends"] is not None and ends not in rule["ends"]:
        errors.append(f"{where}: {rel_type} 不允许 {ends[0]} → {ends[1]}；允许 {rule['ends']}")
    given = {k for k, v in props.items() if v not in (None, "", [])}
    if unknown := set(props) - REL_PROPS:
        errors.append(f"{where}: 关系没有属性 {sorted(unknown)}")
    if missing := rule["required"] - given:
        errors.append(f"{where}: {rel_type} 缺少 {sorted(missing)}")
    for k in given & {"role", "stance", "verdict"}:
        if k not in rule["enums"]:
            errors.append(f"{where}: {rel_type} 没有属性 {k}")
        elif props[k] not in rule["enums"][k]:
            errors.append(f"{where}: {k}={props[k]!r} 不在 {sorted(rule['enums'][k])} 中")
    if rule["anchor"] == "required" and "anchor" not in given:
        errors.append(f"{where}: {rel_type} 需要 anchor")
    if "anchor" in given:
        errors += _check_anchors(props["anchor"], where)
    return errors
