"""MinerU OCR：一篇 PDF 进，Markdown 出。

    from utils.mineru import ocr_pdf, aocr_pdf

    md = ocr_pdf("paper.pdf")          # 普通脚本
    md = await aocr_pdf("paper.pdf")   # notebook / 已有事件循环里
"""

from .ocr import aocr_pdf, ocr_pdf
from .service import resolve_server_url

__all__ = ["ocr_pdf", "aocr_pdf", "resolve_server_url"]
