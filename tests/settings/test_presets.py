import uuid

import pytest
from sqlalchemy import select

from app.modules.llm_config.crypto import ApiKeyCipher
from app.modules.llm_config.models import Preset
from app.shared.config import get_settings

DATA = {
    "name": "GPT mini",
    "model_id": "model",
    "base_url": "https://provider.example/v1/",
    "api_key": "test-secret",
}


async def create(client, **changes):
    r = await client.post("/llm/presets", json=DATA | changes)
    assert r.status_code == 201, r.text
    return r.json()


async def test_global_crud_default_order_and_encrypted_keys(client, session):
    assert (await client.get("/llm/presets")).json() == []
    a = await create(client, name=" First ")
    assert a["name"] == "First" and a["is_default"] is True
    assert a["base_url"] == "https://provider.example/v1"
    assert set(a) == {"id", "name", "model_id", "base_url", "is_default"}
    row = await session.scalar(select(Preset).where(Preset.id == uuid.UUID(a["id"])))
    cipher = ApiKeyCipher(get_settings().llm_config_api_key_secret)
    assert row.api_key_encrypted != DATA["api_key"]
    assert cipher.decrypt(row.api_key_encrypted) == DATA["api_key"]
    encrypted = row.api_key_encrypted
    b = await create(client, name="Second")
    c = await create(client, name="Third")
    assert [p["id"] for p in (await client.get("/llm/presets")).json()] == [
        a["id"],
        c["id"],
        b["id"],
    ]
    r = await client.patch(f"/llm/presets/{a['id']}", json={"model_id": "new-model"})
    assert r.status_code == 200 and r.json()["model_id"] == "new-model"
    await session.refresh(row)
    assert row.api_key_encrypted == encrypted
    r = await client.patch(f"/llm/presets/{a['id']}", json={"api_key": "replacement"})
    assert r.status_code == 200 and "replacement" not in r.text
    await session.refresh(row)
    assert cipher.decrypt(row.api_key_encrypted) == "replacement"
    assert (await client.patch(f"/llm/presets/{a['id']}", json={})).status_code == 200
    r = await client.put(f"/llm/presets/{b['id']}/default")
    assert r.status_code == 200 and r.json()["is_default"]
    assert (await client.put(f"/llm/presets/{b['id']}/default")).status_code == 200
    assert (await client.delete(f"/llm/presets/{b['id']}")).status_code == 204
    presets = (await client.get("/llm/presets")).json()
    assert presets[0]["id"] == c["id"] and presets[0]["is_default"]
    assert sum(p["is_default"] for p in presets) == 1
    for p in presets:
        assert (await client.delete("/llm/presets/" + p["id"])).status_code == 204
    assert (await client.get("/llm/presets")).json() == []


async def test_names_unique_case_insensitively_and_conflict_does_not_poison_transaction(
    client,
):
    a = await create(client, name="Alpha")
    b = await create(client, name="Beta")
    r = await client.post("/llm/presets", json=DATA | {"name": " ALPHA "})
    assert r.status_code == 409
    assert r.json() == {
        "code": "preset_name_taken",
        "error_code": "LLM_003",
        "field": "name",
    }
    r = await client.patch(
        f"/llm/presets/{b['id']}", json={"name": "alpha", "model_id": "lost"}
    )
    assert r.status_code == 409
    assert (
        await client.patch(f"/llm/presets/{a['id']}", json={"name": "Alpha"})
    ).status_code == 200
    assert (
        next(
            p for p in (await client.get("/llm/presets")).json() if p["id"] == b["id"]
        )["model_id"]
        == "model"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", " "),
        ("name", "x" * 81),
        ("model_id", ""),
        ("base_url", "ftp://example.com"),
        ("base_url", "https://"),
        ("api_key", ""),
    ],
)
async def test_invalid_preset_fields(client, field, value):
    r = await client.post("/llm/presets", json=DATA | {field: value})
    assert r.status_code == 422
    assert r.json() == {
        "code": "preset_invalid",
        "error_code": "LLM_002",
        "field": field,
    }


@pytest.mark.parametrize("body", [{"name": None}, {"is_default": True}, {"name": 123}])
async def test_invalid_patch_request(client, body):
    p = await create(client)
    r = await client.patch("/llm/presets/" + p["id"], json=body)
    assert r.status_code == 422
    assert r.json() == {"code": "invalid_request", "error_code": "REQ_001"}


@pytest.mark.parametrize(
    "method,suffix,body",
    [("patch", "", {}), ("put", "/default", None), ("delete", "", None)],
)
async def test_missing_and_invalid_ids(client, method, suffix, body):
    kwargs = {"json": body} if body is not None else {}
    r = await client.request(method, f"/llm/presets/{uuid.uuid4()}{suffix}", **kwargs)
    assert r.status_code == 404
    assert r.json() == {"code": "preset_not_found", "error_code": "LLM_001"}
    r = await client.request(method, f"/llm/presets/not-uuid{suffix}", **kwargs)
    assert r.status_code == 422
    assert r.json()["error_code"] == "REQ_001"
