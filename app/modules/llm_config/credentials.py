"""Public read-only access to saved preset credentials for other modules (wired in shared.deps).

Each lookup is its own short transaction, so callers can contact the provider afterwards
without holding a database connection.
"""

import uuid
from dataclasses import dataclass, field

from app.modules.llm_config.crypto import ApiKeyCipher
from app.modules.llm_config.models import Preset
from app.modules.llm_config.ports import PresetUow


@dataclass(frozen=True)
class PresetCredential:
    name: str
    model_id: str
    base_url: str
    api_key: str = field(repr=False)


class SavedPresetCredentials:
    def __init__(self, uow: PresetUow, cipher: ApiKeyCipher):
        self._uow, self._cipher = uow, cipher

    async def default(self) -> PresetCredential | None:
        async with self._uow() as repo:
            return self._credential(await repo.default())

    async def get(self, preset_id: uuid.UUID) -> PresetCredential | None:
        async with self._uow() as repo:
            return self._credential(await repo.get(preset_id))

    def _credential(self, preset: Preset | None) -> PresetCredential | None:
        if preset is None:
            return None
        return PresetCredential(
            name=preset.name,
            model_id=preset.model_id,
            base_url=preset.base_url,
            api_key=self._cipher.decrypt(preset.api_key_encrypted),
        )
