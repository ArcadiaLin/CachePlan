# utils/mineru · PDF → Markdown

把一篇 PDF 送进**本地 MinerU2.5-Pro vLLM 服务**做版面识别与抽取，返回 Markdown。
只有一个函数，供其它实验调用；来源是 `tmps/e08/ocr_all.py`（E08 的 20 篇一次性跑通）
里的单篇流程，批处理、跳过已有、记账那些都留给调用方。

## 前置

- 服务地址写在本目录 `.env` 的 `mineru_service=`（见 `.env.example`；`.env` 不进版本管理）。
  也可用环境变量 `MINERU_SERVICE` 或 `server_url=` 参数覆盖，三者优先级依次为
  参数 > 环境变量 > `.env`。找不到就抛 `RuntimeError`，不会悄悄回落到 localhost。
- 渲染需要系统二进制 `mutool`：Debian/Ubuntu 上 `apt install mupdf-tools`。
- Python 依赖随仓库根 `make setup` 一起装好；装好后任何实验都能 `from utils.mineru import ...`。
  `utils` 是 PEP 420 命名空间包（`src/utils/` 下没有 `__init__.py`），以后
  `experiments/utils/` 再加工具就各自一个 member、各自 `src/utils/<name>/`，
  并进同一个 `utils.*`，彼此不覆盖。

## 用法

一次一篇，返回 Markdown 字符串，不落盘：

```python
from utils.mineru import ocr_pdf

md = ocr_pdf("tmps/e08/DIGRA - A Dynamic Graph Indexing ....pdf")
```

在 notebook 里（已有事件循环，`asyncio.run` 会失败）用异步版：

```python
from utils.mineru import aocr_pdf

md = await aocr_pdf(pdf_path)
```

可选参数两者相同：`server_url`（覆盖 .env）、`env_file`、`dpi`（默认 200）、
`concurrency`（单篇内的页面并发度，默认 24）、`http_timeout`（默认 900 秒）。
客户端按 `(地址, 并发, 超时)` 缓存，连着跑多篇不会每篇都去握手一次。

出错就抛异常，由调用方决定怎么处理：PDF 不存在 `FileNotFoundError`，
缺 mutool / 渲染失败 / 连不上服务都是 `RuntimeError`，消息里带上下文。

## 产物

没有。函数只返回 Markdown 字符串——写到哪、要不要记录溯源（输入 sha256、页数、
参数、耗时），由调用方按自己实验的记账方式决定。

## 口径

OCR 结果是**机器抽取的文本，不是事实**：表格、公式、图注的还原都可能出错，
任何要进入论断的数字都应回 PDF 原文核对。同一篇重跑两次的结果也不保证逐字相同。
