from typing import Protocol


class PdfInspector(Protocol):
    async def page_count(self, content: bytes, timeout: float) -> int: ...
