import asyncio

from app.modules.llm_config.ports import ConnectionResult


class WaitingPdfInspector:
    def __init__(self):
        self.started = asyncio.Event()

    async def extract_pages(self, content: bytes, timeout: float) -> list[dict]:
        self.started.set()
        await asyncio.Future()
        return 1


class FakeConnectionProbe:
    def __init__(self, result: ConnectionResult, before_call=lambda: None):
        self.result, self.before_call, self.calls = result, before_call, []

    async def test_connection(self, **fields) -> ConnectionResult:
        self.before_call()
        self.calls.append(fields)
        return self.result


class ExtractedTextPdfInspector:
    def __init__(self, text: str, image_percent: float = 0):
        self.text = text
        self.image_percent = image_percent

    async def extract_pages(self, content: bytes, timeout: float) -> list[dict]:
        return [{"text": self.text, "image_percent": self.image_percent}]
