"""节点 id：`<prefix>_<4 位序号>`，按主 Label 顺序分配。"""

from .graph import q

PREFIX = {"Paper": "paper", "Contribution": "contrib", "Method": "method", "MethodConcept": "mc",
          "Task": "task", "Claim": "claim", "ClaimConcept": "cc", "Issue": "issue", "Resource": "res",
          "ResourceRecord": "rr", "Experiment": "exp", "Metric": "metric", "Observation": "obs"}


class IdAllocator:
    """起点是图中该前缀已用的最大序号；同一次写入内共用一个实例。"""

    def __init__(self):
        self.last = {}
        for label, prefix in PREFIX.items():
            rows = q(f"MATCH (n:{label}) WHERE n.id STARTS WITH $p RETURN max(toInteger(substring(n.id, size($p)))) AS m",
                     p=prefix + "_")
            self.last[label] = rows[0]["m"] or 0

    def new(self, label: str) -> str:
        self.last[label] += 1
        return f"{PREFIX[label]}_{self.last[label]:04d}"
