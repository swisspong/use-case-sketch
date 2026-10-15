import asyncio

from app.modules.llm_config.ports import ConnectionResult


class WaitingPdfInspector:
    def __init__(self):
        self.started = asyncio.Event()

    async def page_count(self, content: bytes, timeout: float) -> int:
        self.started.set()
        await asyncio.Future()
        return 1

class FakeConnectionProbe:
    def __init__(self, result: ConnectionResult, before_call=lambda:None):
        self.result, self.before_call, self.calls = result, before_call, []

    async def test_connection(self, **fields) -> ConnectionResult:
        self.before_call()
        self.calls.append(fields)
        return self.result
