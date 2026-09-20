# E08 · schema 设计用的论文语料

为新方向的 schema 设计准备一批论文及其可下载入口。现状是两条来源：

- `papers.yml` —— 手挑的 6 篇初始样本（学习型索引 / 向量搜索 / 时间序列预测），
  用于观察 schema 要覆盖哪些字段。不代表 AgenticScholar 的原始语料。
- `data/raw/e08/raw_html/` —— 浏览器另存的 Semantic Scholar 检索结果页快照，
  由 `notebooks/00_serp_pdf_urls.ipynb` 解析出每条结果的元数据与候选 PDF URL。

## 布局

    papers.yml            手挑样本
    notebooks/            探索面：解析、切片、覆盖率统计
    notebooks/_scratch/   notebook 导出的中间结果，不进版本管理
    src/e08/              流水线脚本（尚空）

## 现在还不是什么

`notebooks/` 是探索面，不是流水线：解析逻辑还没有脚本化，也没有产物写进
`data/processed/e08/`。按 AGENTS.md，等某段解析成为文档引用的数字的来源时，
再把它提升为 `src/e08/pN_*.py`，并给 Makefile 加上可失败的复现目标。

快照口径：S2 的排序、开放获取徽章都随时间变化，HTML 文件名里的日期（或文件
mtime）就是快照时刻；解析出的 `pdf_url` 是页面声明的链接，不等于已验证可下载。
