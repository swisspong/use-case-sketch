"""HTTP schemas shared by several llm_config slices (slice-only schemas stay in their slice)."""

from pydantic import BaseModel

from app.modules.llm_config.models import Preset


class PresetOut(BaseModel):
    """The api_key is write-only: it is never sent back."""

    id: str
    name: str
    model_id: str
    base_url: str
    is_default: bool

    @classmethod
    def of(cls, p: Preset) -> "PresetOut":
        return cls(
            id=str(p.id),
            name=p.name,
            model_id=p.model_id,
            base_url=p.base_url,
            is_default=p.is_default,
        )
