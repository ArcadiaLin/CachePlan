"""种子入库入口：按 SEED_ORDER 读种子文件，逐批经 Commit（operators/commit.py）写入 neo4j-e09。

    uv run python -m e09.seed     # 即 make seed；重跑无副作用，有冲突或复核失败时返回非零
"""

import sys

import yaml

from .config import SEEDS
from .env_check import check_graph
from .operators.commit import apply_plan, check_seed, plan_seed, summary
from .utils.graph import driver, ensure_schema
from .utils.ids import IdAllocator

# id 按写入顺序分配；固定顺序，从空库重演才得到相同的 id
SEED_ORDER = ["tsf.yml", "rag.yml"]


def load_seed(path) -> dict:
    return check_seed(yaml.safe_load(path.read_text(encoding="utf-8")), path.name)


def main() -> int:
    files = {p.name for p in SEEDS.glob("*.yml")}
    if files != set(SEED_ORDER):
        print(f"错误：种子文件 {sorted(files)} 与 SEED_ORDER {SEED_ORDER} 不一致", file=sys.stderr)
        return 1
    if errors := check_graph():   # 与 neo4j-e08 端口相同，写之前确认不是 v1 库
        print(f"错误：{errors}", file=sys.stderr)
        return 1
    try:
        batches = [load_seed(SEEDS / f) for f in SEED_ORDER]   # 全部先过文件检查，再写
    except AssertionError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    ensure_schema()
    ids = IdAllocator()
    for b in batches:
        p = plan_seed(b)
        print(summary(p))
        for c in p.conflicts:
            print(f"  冲突 {c['rule']}：{c['ref']} {c['what']} ← {c['holders']}", file=sys.stderr)
        if p.conflicts:
            return 1
        apply_plan(p, ids)
    driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
