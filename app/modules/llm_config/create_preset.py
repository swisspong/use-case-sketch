"""Create a global model preset.
SPEC
- [x] Valid fields are trimmed; URLs normalized; API keys encrypted and write-only (L2 + L3).
- [x] Names are unique ignoring case; first preset becomes default (L3 + DB).
- [x] POST returns 201 without authentication (endpoint).
"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.modules.llm_config import rules
from app.modules.llm_config.crypto import ApiKeyCipher
from app.modules.llm_config.errors import DefaultPresetConflict
from app.modules.llm_config.models import Preset
from app.modules.llm_config.repository import PresetRepo
from app.modules.llm_config.schemas import PresetOut
from app.shared.deps import SessionDep, SettingsDep


class CreatePresetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr
    model_id: StrictStr
    base_url: StrictStr
    api_key: StrictStr = Field(repr=False)


async def create_preset(
    data: CreatePresetIn, repo: PresetRepo, cipher: ApiKeyCipher
) -> Preset:
    fields = rules.clean_preset_fields(data.model_dump())
    encrypted = cipher.encrypt(fields.pop("api_key"))
    if not await repo.try_lock_configuration():
        raise DefaultPresetConflict
    return await repo.add(
        Preset(
            **fields,
            api_key_encrypted=encrypted,
            is_default=not await repo.has_default(),
        )
    )


router = APIRouter()


@router.post("/llm/presets", status_code=201, response_model=PresetOut)
async def create_preset_endpoint(
    data: CreatePresetIn, session: SessionDep, settings: SettingsDep
) -> PresetOut:
    return PresetOut.of(
        await create_preset(
            data, PresetRepo(session), ApiKeyCipher(settings.llm_config_api_key_secret)
        )
    )
