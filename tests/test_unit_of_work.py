"""Smoke tests for the multi-transaction wiring (uow_factory) and its test double (uow fixture)."""
import pytest
from sqlalchemy import text

from app.modules.text_quality.models import Thresholds
from app.modules.text_quality.repository import ThresholdsRepo
from app.shared.config import Settings
from app.shared.resources import build_resources, uow_factory


class Probe:
    """Minimal repo for this test only: uses a scratch table, so no module data is committed."""
    def __init__(self, session):
        self.session = session

    async def add(self, n: int) -> None:
        await self.session.execute(text("INSERT INTO uow_probe (n) VALUES (:n)"), {"n": n})

    async def all(self) -> list[int]:
        return list(await self.session.scalars(text("SELECT n FROM uow_probe ORDER BY n")))


async def test_uow_factory_commits_each_block_and_rolls_back_on_error(database_url):
    res = build_resources(Settings(database_url=database_url))
    uow = uow_factory(res, Probe)
    try:
        async with res.engine.begin() as conn:
            await conn.execute(text("CREATE TABLE uow_probe (n int)"))
        async with uow() as repo:
            await repo.add(1)
        with pytest.raises(RuntimeError):
            async with uow() as repo:
                await repo.add(2)
                raise RuntimeError("boom")
        async with uow() as repo:  # a new transaction sees only the committed block
            assert await repo.all() == [1]
    finally:
        async with res.engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS uow_probe"))
        await res.aclose()


async def test_uow_fixture_gives_a_repo_per_block(uow):
    make = uow(ThresholdsRepo)
    async with make() as repo:
        await repo.save_changes({"min_thai_percent": 70}, initial=Thresholds(50, 5, min_text_chars=50, max_image_percent=80))
    async with make() as repo:
        assert (await repo.get()).min_thai_percent == 70
