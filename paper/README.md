# paper/ — SIGMOD 投稿

`make` 出 `main.pdf`，`make check` 核对 SIGMOD 的硬性限制。两条命令都不需要网络，
也不需要 root。

## 为什么有 vendor/acmart/

本机装了 `texlive-publishers`，但它给的是 **acmart v2.12（2024-12-28）**；
`vendor/acmart/` 里是 ACM 官网 Primary Article Template 当前发的
**acmart v2.20（2026-08-16）**。给 2027 年的会投稿应当用当前模板，所以 Makefile 通过
`TEXINPUTS` / `BSTINPUTS` 让 vendor 优先，系统那份只在 `vendor/` 缺失时兜底
（`main.log` 里能看到实际加载的是哪一份）。

顺带的好处是：任何装了基础 TeX Live 的机器都能原样编译，不需要联网也不需要 root。
代价是升版要手动换一次文件。

按 acmart 的分发条款，`.cls` 必须与生成它的 `.dtx` / `.ins` 一同分发，所以那两个
源文件也在目录里 —— 它们不参与编译。

升级方式：从 <https://www.acm.org/publications/proceedings-template> 重新下载
`acmart-primary.zip`，取出 `acmart.cls`、`ACM-Reference-Format.bst`、
`acm-jdslogo.png`、`acmart.dtx`、`acmart.ins` 覆盖本目录，然后 `make check` 复核页数。

## 参考文献

`refs.bib` 是**生成物**（已 gitignore），由 `tools/strip-notes.py` 从
`../references/refs.bib` 剥掉 `note` 字段而来。仓库约定每个 bib 条目带一条中文
`note` 说明它支撑哪个问题，而 `ACM-Reference-Format.bst` 会把 `note` 排进参考文献表，
pdflatex 遇到中文直接 fatal。文献元数据只在 `references/refs.bib` 里改。

## 投稿前

`main.tex` 顶部按 SIGMOD 2027 CFP 设了 `sigconf,review,anonymous`，并清掉了投稿期
不该出现的版权块。`make check` 卡两条硬限制：正文 ≤ 12 页（参考文献不计）、
PDF ≤ 10 MB。页数从 `\label{endofbody}` 的页码读，那个标签必须一直紧贴参考文献之前。

双盲的其余部分机器管不了，得自己过一遍：正文、图表、致谢、脚注、URL、自引措辞里
不得留身份线索；资助来源在投稿版一个字都不能提。
