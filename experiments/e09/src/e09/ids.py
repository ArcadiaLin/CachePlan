"""对象 id：`<kind 前缀>_<4 位序号>`，按 kind 顺序分配。"""

from .graph import q
from .schema import FAMILY, PREFIX


class IdAllocator:
    """起点是图中该前缀已用的最大序号；同一次运行内共用一个实例。分配后写入失败只留空号，不会重号。"""

    def __init__(self):
        self.last = {}
        for kind, prefix in PREFIX.items():
            rows = q(f"MATCH (n:{FAMILY[kind]}:{kind}) WHERE n.id STARTS WITH $p "
                     "RETURN max(toInteger(substring(n.id, size($p)))) AS m", p=prefix + "_")
            self.last[kind] = rows[0]["m"] or 0

    def new(self, kind: str) -> str:
        self.last[kind] += 1
        return f"{PREFIX[kind]}_{self.last[kind]:04d}"
