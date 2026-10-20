import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.llm_config.errors import DefaultPresetConflict
from app.modules.llm_config.models import Preset
from app.modules.llm_config.repository import PresetRepo
from app.modules.text_quality.errors import ThresholdOutOfRange
from app.modules.text_quality.models import TextQualityThresholds
from app.modules.text_quality.rules import check_thresholds


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_thai_percent", 65.5),
        ("max_thai_percent", -1),
        ("max_garbled_thai_percent", 101),
        ("min_text_chars", -1),
        ("min_text_chars", 0.1),
        ("max_image_percent", 101),
    ],
)
def test_threshold_rules_are_pure(field, value):
    with pytest.raises(ThresholdOutOfRange) as error:
        check_thresholds({field: value})
    assert error.value.field == field


async def test_database_rejects_bad_thresholds_and_multiple_rows(session):
    fields = {
        "max_thai_percent": 50,
        "max_garbled_thai_percent": 5,
        "min_text_chars": 50,
        "max_image_percent": 80,
    }
    for changes in [{"id": 2}, {"max_thai_percent": 101}, {"min_text_chars": -1}]:
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(TextQualityThresholds(**({"id": 1} | fields | changes)))


async def test_database_unique_index_rejects_two_defaults(session):
    repo = PresetRepo(session)

    def preset(name):
        return Preset(
            name=name,
            model_id="m",
            base_url="https://x/v1",
            api_key_encrypted="encrypted",
            is_default=True,
        )

    await repo.add(preset("one"))
    with pytest.raises(DefaultPresetConflict):
        await repo.add(preset("two"))
    assert len(await repo.list_presets()) == 1


async def test_concurrent_configuration_mutation_returns_conflict(client, engine):
    async with engine.connect() as conn:
        transaction = await conn.begin()
        other = AsyncSession(bind=conn)
        try:
            assert await PresetRepo(other).try_lock_configuration()
            response = await client.post(
                "/llm/presets",
                json={
                    "name": "one",
                    "model_id": "m",
                    "base_url": "https://x/v1",
                    "api_key": "key",
                },
            )
            assert response.status_code == 409
            assert response.json() == {
                "code": "default_preset_conflict",
                "error_code": "LLM_004",
            }
            assert (await client.get("/llm/presets")).json() == []
        finally:
            await other.close()
            await transaction.rollback()
