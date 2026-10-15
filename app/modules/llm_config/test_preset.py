"""Test saved credentials with temporary overrides.
SPEC
- [x] Loads and decrypts saved key in a short transaction, then calls provider outside it (L3 + port).
- [x] Overrides never persist; missing preset returns LLM_001 (endpoint).
"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.modules.llm_config.crypto import ApiKeyCipher
from app.modules.llm_config.errors import PresetNotFound
from app.modules.llm_config.ports import ConnectionProbe, ConnectionResult, PresetUow
from app.modules.llm_config.rules import clean_preset_fields
from app.shared.deps import ConnectionProbeDep, PresetUowDep, SettingsDep


class TestPresetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: StrictStr = ""
    base_url: StrictStr = ""
    api_key: StrictStr = Field(default="", repr=False)


async def test_preset(
    preset_id: uuid.UUID,
    data: TestPresetIn,
    uow: PresetUow,
    cipher: ApiKeyCipher,
    probe: ConnectionProbe,
) -> ConnectionResult:
    overrides = clean_preset_fields(data.model_dump(exclude_unset=True))
    async with uow() as repo:
        preset = await repo.get(preset_id)
        if preset is None:
            raise PresetNotFound
        fields = {
            "model_id": preset.model_id,
            "base_url": preset.base_url,
            "api_key": cipher.decrypt(preset.api_key_encrypted),
        } | overrides
    return await probe.test_connection(**fields)


router = APIRouter()


@router.post("/llm/presets/{preset_id}/test")
async def test_preset_endpoint(
    preset_id: uuid.UUID,
    uow: PresetUowDep,
    settings: SettingsDep,
    probe: ConnectionProbeDep,
    data: TestPresetIn | None = None,
) -> dict:
    return (
        await test_preset(
            preset_id,
            data or TestPresetIn(),
            uow,
            ApiKeyCipher(settings.llm_config_api_key_secret),
            probe,
        )
    ).as_dict()
