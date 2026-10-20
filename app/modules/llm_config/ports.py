from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Literal, Protocol

from app.modules.llm_config.repository import PresetRepo

PresetUow = Callable[[], AbstractAsyncContextManager[PresetRepo]]


@dataclass(frozen=True)
class ConnectionResult:
    ok: bool
    latency_ms: int | None = None
    field: Literal["api_key", "model_id", "base_url"] | None = None
    reason: (
        Literal["unauthorized", "model_not_found", "unreachable", "upstream_error"]
        | None
    ) = None
    upstream_status: int | None = None

    def as_dict(self) -> dict:
        if self.ok:
            return {"ok": True, "latency_ms": self.latency_ms}
        result = {"ok": False, "field": self.field, "reason": self.reason}
        if self.upstream_status is not None:
            result["upstream_status"] = self.upstream_status
        return result


class ConnectionProbe(Protocol):
    async def test_connection(
        self, *, model_id: str, base_url: str, api_key: str
    ) -> ConnectionResult: ...
