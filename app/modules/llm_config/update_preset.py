"""Update a global preset.
SPEC
- [x] Partial update preserves omitted values and key; {} is a no-op (L3).
- [x] Replacement key is encrypted; conflicting names roll back every field (L3).
- [x] Null, unknown fields, invalid IDs and values map to contract errors (endpoint).
"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.modules.llm_config import rules
from app.modules.llm_config.crypto import ApiKeyCipher
from app.modules.llm_config.errors import DefaultPresetConflict, PresetNotFound
from app.modules.llm_config.models import Preset
from app.modules.llm_config.repository import PresetRepo
from app.modules.llm_config.schemas import PresetOut
from app.shared.deps import SessionDep, SettingsDep


class UpdatePresetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr = ""
    model_id: StrictStr = ""
    base_url: StrictStr = ""
    api_key: StrictStr = Field(default="", repr=False)


async def update_preset(
    preset_id: uuid.UUID, data: UpdatePresetIn, repo: PresetRepo, cipher: ApiKeyCipher
) -> Preset:
    changes = rules.clean_preset_fields(data.model_dump(exclude_unset=True))
    if not await repo.try_lock_configuration():
        raise DefaultPresetConflict
    preset = await repo.get(preset_id)
    if preset is None:
        raise PresetNotFound
    if "api_key" in changes:
        changes["api_key_encrypted"] = cipher.encrypt(changes.pop("api_key"))
    await repo.apply_changes(preset, changes)
    return preset


router = APIRouter()


@router.patch("/llm/presets/{preset_id}", response_model=PresetOut)
async def update_preset_endpoint(
    preset_id: uuid.UUID,
    data: UpdatePresetIn,
    session: SessionDep,
    settings: SettingsDep,
) -> PresetOut:
    return PresetOut.of(
        await update_preset(
            preset_id,
            data,
            PresetRepo(session),
            ApiKeyCipher(settings.llm_config_api_key_secret),
        )
    )
