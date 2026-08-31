# references/

外部材料的本地副本。**我们自己写的东西不放这里**——对文献的判断和笔记在 [`docs/literature/`](../docs/literature/)。

## 目录

| 路径 | 是否入库 | 内容 |
|---|---|---|
| `refs.bib` | 入库 | 唯一的文献元数据来源。将来写论文直接用这个文件。 |
| `papers/` | **不入库**（gitignored） | PDF 本体，`<citekey>.pdf` |
| `repos/` | **不入库**（gitignored） | 参考实现的本地 clone |
| `datasets/` | **不入库**（gitignored） | 外部数据集本地副本 |

PDF、clone、数据集不入库的原因是体积与版权；元数据入库是为了可追溯和复现。别人 clone 本仓库后，靠 `refs.bib` 里的 `url` / `doi` 就能自己取回全部原始材料。

## citekey 约定

一篇论文在仓库里的三个位置用同一个 **citekey** 机械绑定，不需要额外的映射表：

```
refs.bib 中的条目名      →  chen2024promptcache
references/papers/       →  chen2024promptcache.pdf
docs/literature/         →  chen2024promptcache.md   （只有需要写笔记时才有）
```

citekey 格式：**第一作者姓氏（小写）+ 发表年份 + 一个关键词**，如 `chen2024promptcache`、`zheng2024sglang`。重复时在年份后加 `a`/`b`。

## 精读稿的暂存位置

用 `paper-close-read` skill 产出的图文精读稿，先落在工作目录里：

```
references/papers/<citekey>/close-read.md      # 精读稿
references/papers/<citekey>/assets/            # 正文引用的图
references/papers/<citekey>/evidence_map.md    # 证据地图
```

这一层是 gitignored 的**暂存区**，不是成品。精读稿由 agent 生成，**必须经人工评审确认结论可信之后**，才决定是否以及以什么形式进入 `docs/literature/`——通常是提炼成一篇判断笔记，而不是把长稿整篇搬过去。未经评审的内容不进 `docs/`，`refs.bib` 的 note 字段也不写它的结论。

## 入库门槛

一篇论文进入 `refs.bib`，必须能说出它支撑哪个 open question / decision / experiment。**不做无目的的文献囤积**——只读不入库是允许的，读完发现无关就不要留下痕迹。

## BibTeX 条目要求

除标准字段外，每个条目补一条 `note` 字段，写明它在本项目中的用途（对应哪个问题），一句话即可：

```bibtex
@inproceedings{chen2024promptcache,
  title     = {...},
  author    = {...},
  booktitle = {...},
  year      = {2024},
  url       = {https://arxiv.org/abs/xxxx.xxxxx},
  note      = {支撑 open-questions/Necessity-of-agentic-execution：...}
}
```
