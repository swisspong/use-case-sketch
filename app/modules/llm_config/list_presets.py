"""List global presets.
SPEC
- [x] Default first, then newest first; empty list is []; never expose keys (L3 + endpoint).
"""

from fastapi import APIRouter

from app.modules.llm_config.models import Preset
from app.modules.llm_config.repository import PresetRepo
from app.modules.llm_config.schemas import PresetOut
from app.shared.deps import SessionDep


async def list_presets(repo: PresetRepo) -> list[Preset]:
    return await repo.list_presets()


router = APIRouter()


@router.get("/llm/presets", response_model=list[PresetOut])
async def list_presets_endpoint(session: SessionDep) -> list[PresetOut]:
    return [PresetOut.of(p) for p in await list_presets(PresetRepo(session))]
