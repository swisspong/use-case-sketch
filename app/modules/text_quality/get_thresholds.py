"""Read global thresholds.
SPEC
- [x] Returns persisted values or configured defaults, plus defaults (L4 -> L3).
- [x] GET requires no token (endpoint).
"""

from fastapi import APIRouter

from app.modules.text_quality.models import Thresholds
from app.modules.text_quality.repository import ThresholdsRepo
from app.modules.text_quality.schemas import ThresholdsOut
from app.shared.deps import SessionDep, SettingsDep


async def get_thresholds(repo: ThresholdsRepo, defaults: Thresholds) -> Thresholds:
    return await repo.get() or defaults


router = APIRouter()


@router.get("/text-quality/thresholds", response_model=ThresholdsOut)
async def get_thresholds_endpoint(
    session: SessionDep, settings: SettingsDep
) -> ThresholdsOut:
    defaults = Thresholds.defaults(settings)
    return ThresholdsOut.of(
        await get_thresholds(ThresholdsRepo(session), defaults), defaults
    )
