"""All preset SQL. No commits and no business decisions."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.llm_config.errors import DefaultPresetConflict, PresetNameTaken
from app.modules.llm_config.models import NAME_UNIQUE, ONE_DEFAULT, Preset


class PresetRepo:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def try_lock_configuration(self) -> bool:
        # Serialize mutations across processes, including the empty-list/first-preset case.
        return bool(
            await self._session.scalar(select(func.pg_try_advisory_xact_lock(752041)))
        )

    async def add(self, preset: Preset) -> Preset:
        try:
            async with self._session.begin_nested():
                self._session.add(preset)
        except IntegrityError as e:
            _translate(e)
            raise
        return preset

    async def list_presets(self) -> list[Preset]:
        return list(
            await self._session.scalars(
                select(Preset)
                .order_by(Preset.is_default.desc(), Preset.created_at.desc(), Preset.id)
                .execution_options(populate_existing=True)
            )
        )

    async def has_default(self) -> bool:
        return bool(
            await self._session.scalar(
                select(select(Preset.id).where(Preset.is_default).exists())
            )
        )

    async def get(self, preset_id: uuid.UUID) -> Preset | None:
        return await self._session.get(Preset, preset_id, populate_existing=True)

    async def apply_changes(self, preset: Preset, changes: dict[str, str]) -> None:
        try:
            async with self._session.begin_nested():
                for field, value in changes.items():
                    setattr(preset, field, value)
        except IntegrityError as e:
            _translate(e)
            raise

    async def make_default(self, preset: Preset) -> None:
        try:
            async with self._session.begin_nested():
                await self._session.execute(
                    update(Preset)
                    .where(Preset.id != preset.id, Preset.is_default)
                    .values(is_default=False)
                )
                preset.is_default = True
        except IntegrityError as e:
            _translate(e)
            raise

    async def newest(self) -> Preset | None:
        return await self._session.scalar(
            select(Preset).order_by(Preset.created_at.desc(), Preset.id).limit(1)
        )

    async def delete(self, preset: Preset) -> None:
        await self._session.delete(preset)
        await self._session.flush()


def _translate(e: IntegrityError) -> None:
    constraint = getattr(e.orig.__cause__, "constraint_name", None)
    if constraint == NAME_UNIQUE:
        raise PresetNameTaken from e
    if constraint == ONE_DEFAULT:
        raise DefaultPresetConflict from e
