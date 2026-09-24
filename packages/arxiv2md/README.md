# arxiv2md（vendored fork）

从 [timf34/arxiv2md](https://github.com/timf34/arxiv2md) vendored 而来
（上游 commit `f662652`，2026-06-16，MIT，见 `LICENSE`；只读原副本在
`references/repos/arxiv2md`）。

思路：不解析 PDF，而是抓 arXiv 官方 HTML（`arxiv.org/html/<id>`，无 HTML 时回退
ar5iv），用 BeautifulSoup 按 LaTeXML 的结构（`ltx_*` class）序列化成 Markdown。

只复制了库 + CLI（`src/arxiv2md/`），未复制 `server/`、`static/`、部署文件。

## 与上游的差异

1. **页内锚点与跳转**。上游把 `#bib.bibN` 引文链接剥成纯文本；本版输出
   `[12](#bib.bib12)`，并为链接目标插入 `<a id="…" name="…"></a>` 锚点（沿用
   LaTeXML 的 id）：参考文献条目（`bib.bibN`）、章节标题（`S3.SS2`、`A1`…）、
   图与子图面板（`S3.F1`、`A2.F14.sf4`）、表（`S4.T1`）、公式（`S3.E1`）。
   最终输出里目标不存在的 `[text](#frag)`（被章节过滤或 `remove_refs` 删掉、
   或原文本身悬空）降级为纯文本，保证没有死链。
2. **图片内嵌**。上游把图片降级成纯文本；本版输出 `![图注](url)` 内嵌图片，
   支持 `<img>` 和 LaTeXML 的 SVG `<object data>` 两种形式，多子图 figure 全保留；
   alt 用图注的纯文本（去掉链接、转义方括号），不破坏图片语法；有子图时图注取
   外层 figure 自己的 caption，而不是第一个子图的 "(a) …"。修复了老论文 src
   自带论文 id 前缀导致 URL 拼接 404 的问题。
   `--download-images`（库接口为 `download_images_to` 参数）会把图片下载到
   `<输出名>.images/` 并把链接改写为相对路径；单张下载失败只记 warning、保留
   远程 URL，不中断转换。
3. **行间公式**。上游把公式表整体摊平成 `$$ $...$ (1) $$`（嵌套美元符，KaTeX
   解析失败）。本版在 MathML 被摊平之前按 LaTeXML 表结构逐个公式转换：一个
   `<tbody>`（一条公式）→ 一个 `$$` 块，同一行的左右对齐单元格合并进同一条公式，
   多行公式用 `aligned`，编号转 `\tag{n}`（支持 `(A.1)`、`(3a)` 这类编号），
   单元格里的散文字用 `\text{}`。`$$` 独占一行，兼容 remark-math 等要求块级
   分隔符的渲染器。每个块生成时做结构自检（`$`、花括号、`\begin/\end` 配对），
   异常记 warning。
4. **表格合并单元格**。上游清掉单元格全部属性（含 `rowspan`/`colspan`），合并单元格
   之后的值整体左移错列。本版保留这两个属性并按网格展开：合并单元格的文字只出现在
   左上角，被覆盖的位置留空，每个值都落在自己的列头下；单元格内的 `|` 转义。
5. **不再丢内容**。上游的块级序列化会丢掉不在 `<p>` 里的文字，figure 里除图注/图片/
   表格之外的内容也全部丢弃（算法正文、代码/prompt 块、SVG 文本框、表下脚注列表、
   子图注）。本版把块容器里的散文字收成段落，figure 处理完图注/图片/表格后剩余内容
   走通用块序列化；子图注输出为 `Subfigure: …`；外层 figure 只用自己的图注。
6. **代码块**。`ltx_lstlisting` 与 `<pre>` 输出为围栏代码块（带 LaTeXML 记录的语言），
   内容优先取 LaTeXML 内嵌的源码（`ltx_listing_data` 的 base64 数据，保留缩进，去掉
   公共缩进），没有时退回渲染行。否则 prompt 里的 `## …`、`- …` 会被当成 Markdown
   标题和列表。引用块（blockquote）按块序列化，内部的段落/代码块保持结构。
   算法（algorithmic）也输出为代码块（面向 Agent 而非人类读者）：保留行号和 `$…$`
   公式原文；LaTeXML 只把嵌套层级编码成不同宽度的 Unicode 空格（em/en/hair 空格
   组合），这里按宽度折算、以列表内最小非零缩进为一级，还原成 4 空格缩进。
7. **默认值**。库接口 `ingest_paper` / `ingest_paper_sync` 的 `remove_refs` 和
   `remove_inline_citations` 默认改为 `False`（上游为 `True`），否则引文锚点
   没有落点。CLI 的 `--remove-*` 开关行为不变（默认即保留）。
8. **依赖裁剪**。去掉 tiktoken（仅用于 token 估算，缺失时自动跳过）和
   python-dotenv（上游未实际使用）。

## 用法

```bash
# CLI（在仓库根的共享 .venv 下）
uv run arxiv2md 2501.11120v1 -o paper.md

# 下载图片到 paper.images/，Markdown 里改为相对路径引用
uv run arxiv2md 2501.11120v1 --download-images -o paper.md

# 库
from arxiv2md import ingest_paper_sync
result = ingest_paper_sync("2501.11120v1", download_images_to="paper.images")
```

抓取的 HTML 缓存在 `$ARXIV2MD_CACHE_PATH`（默认 `./.arxiv2md_cache/`，已入根
`.gitignore`）。

## 测试

```bash
uv run pytest packages/arxiv2md
```
