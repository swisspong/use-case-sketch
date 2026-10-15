"""Delete a global preset.
SPEC
- [x] Deleting default promotes newest remaining preset; deleting last gives [] (L3).
- [x] DELETE returns 204; missing preset returns LLM_001 (endpoint).
"""

import uuid

from fastapi import APIRouter

from app.modules.llm_config.errors import DefaultPresetConflict, PresetNotFound
from app.modules.llm_config.repository import PresetRepo
from app.shared.deps import SessionDep


async def delete_preset(preset_id: uuid.UUID, repo: PresetRepo) -> None:
    if not await repo.try_lock_configuration():
        raise DefaultPresetConflict
    preset = await repo.get(preset_id)
    if preset is None:
        raise PresetNotFound
    was_default = preset.is_default
    await repo.delete(preset)
    if was_default and (newest := await repo.newest()):
        await repo.make_default(newest)


router = APIRouter()


@router.delete("/llm/presets/{preset_id}", status_code=204)
async def delete_preset_endpoint(preset_id: uuid.UUID, session: SessionDep) -> None:
    await delete_preset(preset_id, PresetRepo(session))
