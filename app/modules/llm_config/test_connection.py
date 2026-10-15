"""Test unsaved connection credentials without persistence.
SPEC
- [x] Validates fields before calling the provider and returns a result (L2 + port).
- [x] Never persists credentials or test results (endpoint).
"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.modules.llm_config.ports import ConnectionProbe, ConnectionResult
from app.modules.llm_config.rules import clean_preset_fields
from app.shared.deps import ConnectionProbeDep


class TestConnectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: StrictStr
    base_url: StrictStr
    api_key: StrictStr = Field(repr=False)


async def test_connection(
    data: TestConnectionIn, probe: ConnectionProbe
) -> ConnectionResult:
    fields = clean_preset_fields(data.model_dump())
    return await probe.test_connection(**fields)


router = APIRouter()


@router.post("/llm/presets/test")
async def test_connection_endpoint(
    data: TestConnectionIn, probe: ConnectionProbeDep
) -> dict:
    return (await test_connection(data, probe)).as_dict()
