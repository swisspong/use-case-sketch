"""Browser-test composition root: real API/storage, isolated HTTP provider boundary."""

import asyncio
import json
from contextlib import asynccontextmanager

import httpx

from app.main import create_app
from app.modules.llm_config.adapters.openai_http import OpenAIConnectionProbe

app = create_app()
production_lifespan = app.router.lifespan_context


async def provider_response(request: httpx.Request) -> httpx.Response:
    # All hosts are intercepted. Only this explicit contract can produce success.
    if str(request.url) != "https://e2e-provider.invalid/v1/chat/completions":
        raise httpx.ConnectError("Unknown fixture endpoint", request=request)
    body = json.loads(request.content)
    model = body.get("model")
    expected_key = "rotated-key" if model == "e2e-rotated" else "e2e-key"
    if request.headers.get("authorization") != f"Bearer {expected_key}":
        return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})
    messages = body.get("messages", [])
    if (
        body.get("max_tokens") != 1
        or len(messages) != 1
        or messages[0].get("role") != "user"
        or not isinstance(messages[0].get("content"), str)
    ):
        return httpx.Response(400, json={"error": {"code": "invalid_request"}})
    if model == "e2e-rate-limit":
        return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
    if model == "e2e-unavailable":
        return httpx.Response(503, json={"error": {"code": "unavailable"}})
    if model == "e2e-malformed":
        return httpx.Response(200, text="<h1>Not a chat completion</h1>")
    if model == "e2e-timeout":
        await asyncio.sleep(
            11
        )  # Longer than the production adapter's total 10-second deadline.
    if model not in ("e2e-ok", "e2e-ok-alias", "e2e-rotated"):
        return httpx.Response(404, json={"error": {"code": "model_not_found"}})
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": "x"}}]}
    )


@asynccontextmanager
async def lifespan(application):
    async with production_lifespan(application):
        await application.state.res.connection_probe.aclose()
        application.state.res.connection_probe = OpenAIConnectionProbe(
            transport=httpx.MockTransport(provider_response)
        )
        yield


app.router.lifespan_context = lifespan
