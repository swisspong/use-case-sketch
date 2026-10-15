import uuid

import httpx
import pytest

from app.modules.llm_config.adapters.openai_http import OpenAIConnectionProbe
from app.modules.llm_config.ports import ConnectionResult
from app.modules.llm_config.repository import PresetRepo
from app.shared.deps import get_connection_probe, get_preset_uow
from tests.fakes import FakeConnectionProbe
from tests.settings.test_presets import create


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (200, {"choices": [{"message": {"content": "x"}}]}, {"ok": True}),
        (
            401,
            {},
            {
                "ok": False,
                "field": "api_key",
                "reason": "unauthorized",
                "upstream_status": 401,
            },
        ),
        (
            403,
            {},
            {
                "ok": False,
                "field": "api_key",
                "reason": "unauthorized",
                "upstream_status": 403,
            },
        ),
        (
            404,
            {},
            {
                "ok": False,
                "field": "model_id",
                "reason": "model_not_found",
                "upstream_status": 404,
            },
        ),
        (
            429,
            {},
            {
                "ok": False,
                "field": None,
                "reason": "upstream_error",
                "upstream_status": 429,
            },
        ),
        (
            503,
            {},
            {
                "ok": False,
                "field": None,
                "reason": "upstream_error",
                "upstream_status": 503,
            },
        ),
        (200, {}, {"ok": False, "field": "base_url", "reason": "unreachable"}),
    ],
)
async def test_adapter_translates_provider_and_sends_minimal_request(
    status, body, expected
):
    import json

    calls = []

    def respond(request):
        calls.append(request)
        assert str(request.url) == "https://provider.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer secret"
        data = json.loads(request.content)
        assert (
            data["model"] == "m"
            and data["max_tokens"] == 1
            and len(data["messages"]) == 1
        )
        return httpx.Response(status, json=body)

    probe = OpenAIConnectionProbe(transport=httpx.MockTransport(respond))
    try:
        result = await probe.test_connection(
            model_id="m", base_url="https://provider.example/v1", api_key="secret"
        )
        actual = result.as_dict()
        if expected["ok"]:
            assert actual["ok"] and isinstance(actual["latency_ms"], int)
        else:
            assert actual == expected
        assert len(calls) == 1  # This explicit connection test must not retry.
        assert "secret" not in str(actual)
    finally:
        await probe.aclose()


async def test_adapter_handles_timeout_without_retry():
    calls = []

    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret provider details", request=request)

    probe = OpenAIConnectionProbe(transport=httpx.MockTransport(respond))
    try:
        result = await probe.test_connection(
            model_id="m", base_url="https://x/v1", api_key="secret"
        )
        assert result.as_dict() == {
            "ok": False,
            "field": "base_url",
            "reason": "unreachable",
        }
        assert len(calls) == 1
    finally:
        await probe.aclose()


async def test_test_endpoints_use_saved_key_and_do_not_persist_overrides(
    client, session, uow
):
    p = await create(client)

    def no_transaction():
        assert not session.in_nested_transaction()

    probe = FakeConnectionProbe(
        ConnectionResult(ok=True, latency_ms=12), before_call=no_transaction
    )
    client.app.dependency_overrides[get_connection_probe] = lambda: probe
    client.app.dependency_overrides[get_preset_uow] = lambda: uow(PresetRepo)
    r = await client.post(
        "/llm/presets/test",
        json={"model_id": "new", "base_url": "https://x/v1", "api_key": "temporary"},
    )
    assert r.json() == {"ok": True, "latency_ms": 12}
    r = await client.post(f"/llm/presets/{p['id']}/test", json={"model_id": "override"})
    assert r.status_code == 200 and r.json()["ok"]
    assert probe.calls[-1] == {
        "model_id": "override",
        "base_url": p["base_url"],
        "api_key": "test-secret",
    }
    assert (await client.get("/llm/presets")).json() == [p]
    r = await client.post(f"/llm/presets/{p['id']}/test")
    assert r.status_code == 200
    r = await client.post(
        "/llm/presets/test",
        json={"model_id": "", "base_url": "https://x/v1", "api_key": "k"},
    )
    assert r.status_code == 422 and r.json()["field"] == "model_id"
    assert len(probe.calls) == 3
    r = await client.post(f"/llm/presets/{uuid.uuid4()}/test", json={})
    assert r.status_code == 404 and r.json()["error_code"] == "LLM_001"
