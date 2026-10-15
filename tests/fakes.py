from app.modules.llm_config.ports import ConnectionResult

class FakeConnectionProbe:
    def __init__(self, result: ConnectionResult, before_call=lambda:None):
        self.result, self.before_call, self.calls = result, before_call, []

    async def test_connection(self, **fields) -> ConnectionResult:
        self.before_call()
        self.calls.append(fields)
        return self.result
