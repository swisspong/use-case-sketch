import pytest

DEFAULTS = {
    "max_thai_percent": 50,
    "max_garbled_thai_percent": 5,
    "min_text_chars": 50,
    "max_image_percent": 80,
}


async def test_defaults_and_partial_updates_are_global_and_persistent(client):
    r = await client.get("/text-quality/thresholds")
    assert r.status_code == 200
    assert r.json() == DEFAULTS | {"defaults": DEFAULTS}
    r = await client.patch("/text-quality/thresholds", json={"max_thai_percent": 65.0})
    assert r.status_code == 200
    assert r.json() == DEFAULTS | {"max_thai_percent": 65, "defaults": DEFAULTS}
    r = await client.patch("/text-quality/thresholds", json={"min_text_chars": 0})
    expected = DEFAULTS | {
        "max_thai_percent": 65,
        "min_text_chars": 0,
        "defaults": DEFAULTS,
    }
    assert r.json() == expected
    assert (await client.get("/text-quality/thresholds")).json() == expected
    assert (await client.patch("/text-quality/thresholds", json={})).json() == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_thai_percent", -1),
        ("max_thai_percent", 65.5),
        ("max_garbled_thai_percent", 101),
        ("min_text_chars", -1),
        ("min_text_chars", 1.5),
        ("max_image_percent", 101),
    ],
)
async def test_invalid_value_is_field_error_and_does_not_save(client, field, value):
    r = await client.patch("/text-quality/thresholds", json={field: value})
    assert r.status_code == 422
    assert r.json() == {
        "code": "threshold_out_of_range",
        "error_code": "TQ_001",
        "field": field,
    }
    assert (await client.get("/text-quality/thresholds")).json() == DEFAULTS | {
        "defaults": DEFAULTS
    }


@pytest.mark.parametrize(
    "body",
    [
        {"min_text_chars": None},
        {"max_thai_percent": "65"},
        {"max_image_percent": True},
        {"defaults": {}},
        {"extra": 1},
        {"min_thai_percent": 50},
    ],
)
async def test_bad_request_shape_uses_request_error(client, body):
    r = await client.patch("/text-quality/thresholds", json=body)
    assert r.status_code == 422
    assert r.json() == {"code": "invalid_request", "error_code": "REQ_001"}
