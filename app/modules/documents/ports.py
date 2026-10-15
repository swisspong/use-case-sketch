from typing import Protocol


class PdfInspector(Protocol):
    async def extract_pages(self, content: bytes, timeout: float) -> list[dict]: ...
