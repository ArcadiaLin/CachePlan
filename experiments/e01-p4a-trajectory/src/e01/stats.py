"""最小统计工具。刻意不引入 numpy/pandas —— 主线阶段要能零依赖复现。"""

from __future__ import annotations


def quantiles(values, ps=(0.10, 0.25, 0.50, 0.75, 0.90, 0.99)) -> dict:
    v = sorted(values)
    if not v:
        return {}
    n = len(v)
    out = {"n": n, "mean": sum(v) / n, "min": v[0], "max": v[-1]}
    for p in ps:
        out[f"p{int(p * 100)}"] = v[min(n - 1, int(p * n))]
    return out


def pearson(xs, ys) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
    return num / den if den else None


def fmt(q: dict, name: str) -> str:
    if not q:
        return f"  {name}: (空)"
    return (f"  {name}: n={q['n']} mean={q['mean']:.1f} p10={q['p10']} "
            f"p50={q['p50']} p90={q['p90']} max={q['max']}")
