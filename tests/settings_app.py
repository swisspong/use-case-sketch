"""Browser-test composition root: real API/storage, isolated HTTP provider boundary."""

import asyncio
import json
from contextlib import asynccontextmanager

import httpx

from app.main import create_app
from app.modules.documents.adapters.openai_ocr import OpenAIOcrReader
from app.modules.llm_config.adapters.openai_http import OpenAIConnectionProbe
from app.shared.config import get_settings

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


# OCR models: the model id selects the simulated provider behaviour.
OCR_TEXT = {"e2e-ok": "Hello OCR text", "e2e-ocr-poor": ""}


async def ocr_response(request: httpx.Request) -> httpx.Response:
    if str(request.url) != "https://e2e-provider.invalid/v1/chat/completions":
        raise httpx.ConnectError("Unknown fixture endpoint", request=request)
    if request.headers.get("authorization") != "Bearer e2e-key":
        return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})
    body = json.loads(request.content)
    image = body["messages"][-1]["content"][-1]["image_url"]["url"]
    # The real renderer must have produced a PNG of the page.
    if not image.startswith("data:image/png;base64,iVBORw0KGgo"):
        return httpx.Response(400, json={"error": {"code": "invalid_image"}})
    model = body.get("model")
    if model == "e2e-timeout":
        await asyncio.sleep(get_settings().documents_ocr_timeout_seconds + 1)
    if model == "e2e-unavailable":
        return httpx.Response(503, json={"error": {"code": "unavailable"}})
    if model == "e2e-malformed":
        return httpx.Response(200, text="<h1>Not a chat completion</h1>")
    if model not in OCR_TEXT:
        return httpx.Response(404, json={"error": {"code": "model_not_found"}})
    message = {"role": "assistant", "content": OCR_TEXT[model]}
    return httpx.Response(
        200, json={"choices": [{"finish_reason": "stop", "message": message}]}
    )


@asynccontextmanager
async def lifespan(application):
    async with production_lifespan(application):
        res = application.state.res
        await res.connection_probe.aclose()
        res.connection_probe = OpenAIConnectionProbe(
            transport=httpx.MockTransport(provider_response)
        )
        await res.ocr_reader.aclose()
        res.ocr_reader = OpenAIOcrReader(
            timeout=res.settings.documents_ocr_timeout_seconds,
            transport=httpx.MockTransport(ocr_response),
        )
        yield


app.router.lifespan_context = lifespan
