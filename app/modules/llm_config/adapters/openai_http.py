import asyncio
import time

import httpx

from app.modules.llm_config.ports import ConnectionResult


class OpenAIConnectionProbe:
    def __init__(self, *, transport=None):
        self._client = httpx.AsyncClient(
            timeout=10, transport=transport, follow_redirects=False
        )

    async def test_connection(
        self, *, model_id: str, base_url: str, api_key: str
    ) -> ConnectionResult:
        started = time.monotonic()
        try:
            # Explicit connection tests run once, with a total deadline, as specified in Penpot.
            async with asyncio.timeout(10):
                response = await self._client.post(
                    base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model_id,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "Hi"}],
                    },
                )
        except (httpx.HTTPError, TimeoutError):
            return ConnectionResult(ok=False, field="base_url", reason="unreachable")
        status = response.status_code
        if 200 <= status < 300:
            try:
                payload = response.json()
                choices = payload.get("choices") if isinstance(payload, dict) else None
                valid = (
                    isinstance(choices, list)
                    and choices
                    and isinstance(choices[0], dict)
                    and isinstance(choices[0].get("message"), dict)
                )
            except ValueError:
                valid = False
            if not valid:
                return ConnectionResult(
                    ok=False, field="base_url", reason="unreachable"
                )
            return ConnectionResult(
                ok=True, latency_ms=round((time.monotonic() - started) * 1000)
            )
        if status in (401, 403):
            return ConnectionResult(
                ok=False, field="api_key", reason="unauthorized", upstream_status=status
            )
        if status == 404:
            return ConnectionResult(
                ok=False,
                field="model_id",
                reason="model_not_found",
                upstream_status=status,
            )
        return ConnectionResult(
            ok=False, reason="upstream_error", upstream_status=status
        )

    async def aclose(self):
        await self._client.aclose()
