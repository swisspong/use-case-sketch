"""All DB access for text_quality. One method per real need; never commits (the caller's unit of work does)."""

from dataclasses import asdict, fields

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.text_quality.models import TextQualityThresholds, Thresholds

_ROW_ID = 1  # one system-wide row; the DB enforces it with a CHECK constraint
_FIELDS = [f.name for f in fields(Thresholds)]


class ThresholdsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self) -> Thresholds | None:
        # save_changes is a Core upsert that bypasses the identity map: always reload from the DB
        row = await self.session.get(
            TextQualityThresholds, _ROW_ID, populate_existing=True
        )
        if row is None:
            return None
        return Thresholds(**{f: getattr(row, f) for f in _FIELDS})

    async def save_changes(
        self, changes: dict[str, float | int], initial: Thresholds
    ) -> Thresholds:
        """Apply `changes` atomically. If nothing is saved yet, the row starts from `initial`."""
        t = TextQualityThresholds
        stmt = insert(t).values(id=_ROW_ID, **(asdict(initial) | changes))
        stmt = stmt.on_conflict_do_update(
            index_elements=[t.id],
            # only the sent fields change; no changes is a no-op update that still returns the row
            set_=changes or {"id": stmt.excluded.id},
        ).returning(*(getattr(t, f) for f in _FIELDS))
        row = (await self.session.execute(stmt)).one()
        return Thresholds(**row._mapping)
