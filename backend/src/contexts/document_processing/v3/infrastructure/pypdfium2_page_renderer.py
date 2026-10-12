"""Rasterize one one-based PDF page to PNG with pypdfium2 (PDFium) and Pillow.

Resolution is dpi/72 scale, reduced so the longest side never exceeds
max_side_pixels. Recognized PDFium/encoding failures and nonexistent pages ->
PageRenderingError without library messages. Resources are closed every call.
"""

from io import BytesIO
from math import isfinite

import pypdfium2 as pdfium

from ..application.use_cases.ocr_document_pages.errors import PageRenderingError
from ..application.use_cases.ocr_document_pages.ports import PageImage


class Pypdfium2PageRenderer:
    def __init__(self, *, dpi: float = 200, max_side_pixels: int = 2000) -> None:
        if (type(dpi) not in (int, float) or not isfinite(dpi) or not 0 < dpi <= 1200
                or type(max_side_pixels) is not int or not 0 < max_side_pixels <= 10_000):
            raise ValueError("Invalid render limits")
        self.dpi = dpi
        self.max_side_pixels = max_side_pixels

    def render(self, *, pdf: bytes, page_number: int) -> PageImage:
        try:
            document = pdfium.PdfDocument(pdf)
        except pdfium.PdfiumError:
            raise PageRenderingError("Page rendering unavailable") from None
        try:
            if type(page_number) is not int or not 1 <= page_number <= len(document):
                raise PageRenderingError("Page rendering unavailable")
            page = document[page_number - 1]
            try:
                width, height = page.get_size()
                longest = max(width, height)
                if not longest > 0:
                    raise PageRenderingError("Page rendering unavailable")
                scale = min(self.dpi / 72, self.max_side_pixels / longest)
                bitmap = page.render(scale=scale)
                try:
                    with BytesIO() as buffer:
                        bitmap.to_pil().save(buffer, format="PNG")
                        return PageImage("image/png", buffer.getvalue())
                finally:
                    bitmap.close()
            finally:
                page.close()
        except (pdfium.PdfiumError, OSError, ValueError):
            raise PageRenderingError("Page rendering unavailable") from None
        finally:
            document.close()
