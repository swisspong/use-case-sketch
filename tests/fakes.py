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


class FakePageRenderer:
    def __init__(self, before_call=lambda: None):
        self.before_call, self.calls = before_call, []

    async def render_png(self, content: bytes, number: int) -> bytes:
        self.before_call()
        self.calls.append(number)
        return b"\x89PNG fake"


class FakeOcrReader:
    """Returns queued readings in order; records the preset and image of every call."""

    def __init__(self, *readings, before_call=lambda: None):
        from app.modules.documents.ports import OcrReading

        self.readings = list(readings) or [OcrReading(text="Hello OCR")]
        self.before_call, self.calls = before_call, []

    async def read(self, image: bytes, preset) -> object:
        self.before_call()
        self.calls.append({"image": image, "preset": preset})
        return self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]
