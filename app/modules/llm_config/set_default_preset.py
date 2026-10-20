"""Select the global default.
SPEC
- [x] Selection is atomic and idempotent; exactly one default remains (L3 + DB).
- [x] Unknown preset returns LLM_001 (endpoint).
"""

import uuid

from fastapi import APIRouter

from app.modules.llm_config.errors import DefaultPresetConflict, PresetNotFound
from app.modules.llm_config.models import Preset
from app.modules.llm_config.repository import PresetRepo
from app.modules.llm_config.schemas import PresetOut
from app.shared.deps import SessionDep


async def set_default_preset(preset_id: uuid.UUID, repo: PresetRepo) -> Preset:
    if not await repo.try_lock_configuration():
        raise DefaultPresetConflict
    preset = await repo.get(preset_id)
    if preset is None:
        raise PresetNotFound
    await repo.make_default(preset)
    return preset


router = APIRouter()


@router.put("/llm/presets/{preset_id}/default", response_model=PresetOut)
async def set_default_preset_endpoint(
    preset_id: uuid.UUID, session: SessionDep
) -> PresetOut:
    return PresetOut.of(await set_default_preset(preset_id, PresetRepo(session)))
