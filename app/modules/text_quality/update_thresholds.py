"""Update global thresholds.
SPEC
- [x] Partial updates persist; omitted fields keep their values; {} is a no-op (L3).
- [x] Whole numbers only; percents 0..100, character counts >=0 (L2).
- [x] Null, unknown fields, booleans and strings are invalid requests (endpoint).
"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt

from app.modules.text_quality import rules
from app.modules.text_quality.models import Thresholds
from app.modules.text_quality.repository import ThresholdsRepo
from app.modules.text_quality.schemas import ThresholdsOut
from app.shared.deps import SessionDep, SettingsDep


class UpdateThresholdsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_thai_percent: StrictInt | StrictFloat = 50
    max_garbled_thai_percent: StrictInt | StrictFloat = 5
    min_text_chars: StrictInt | StrictFloat = 50
    max_image_percent: StrictInt | StrictFloat = 80


async def update_thresholds(
    data: UpdateThresholdsIn, repo: ThresholdsRepo, defaults: Thresholds
) -> Thresholds:
    changes = data.model_dump(exclude_unset=True)
    rules.check_thresholds(changes)
    if not changes:
        return await repo.get() or defaults
    return await repo.save_changes(
        {k: int(v) for k, v in changes.items()}, initial=defaults
    )


router = APIRouter()


@router.patch("/text-quality/thresholds", response_model=ThresholdsOut)
async def update_thresholds_endpoint(
    data: UpdateThresholdsIn, session: SessionDep, settings: SettingsDep
) -> ThresholdsOut:
    defaults = Thresholds.defaults(settings)
    return ThresholdsOut.of(
        await update_thresholds(data, ThresholdsRepo(session), defaults), defaults
    )
