"""Administrator-approved model catalogue shared by extraction and text repair.

Names, endpoints and models have the same approval/lookup semantics for both
consumers. VisionPreset keeps its existing name for import compatibility; it
specifies a model invocation target, not proof of vision/text capability.
Each trusted preset carries its own required API key for both consumers. Callers
select only a name; they cannot supply credentials. Keys are invocation-only data,
never domain state, persistence provenance, outcomes or diagnostics. Endpoint
allowlisting and actual provider capability remain adapter responsibilities.
Admin editing/access control is outside these use cases.
"""

from dataclasses import dataclass, field
from urllib.parse import urlsplit


class InvalidModelPresetCatalogue(RuntimeError):
    """Malformed catalogue (including absent/blank key) -> app -> outer handler.

    No dependency I/O or presentation; diagnostics never include preset secrets.

    ExtractionConfig translates this to its existing InvalidExtractionConfiguration
    exception for compatibility; repair propagates this shared exception directly.
    """


@dataclass(frozen=True)
class VisionPreset:
    name: str
    endpoint: str
    model: str
    # Missing JSON field remains representable solely for catalogue rejection.
    # It is not an optional credential: select() must reject missing/blank keys.
    api_key: str = field(default="", repr=False)


@dataclass(frozen=True)
class UnknownVisionPreset:
    """Caller selected a name outside the administrator-approved catalogue."""


@dataclass(frozen=True)
class ModelPresetCatalogue:
    presets: tuple[VisionPreset, ...]

    def select(self, name: str) -> VisionPreset | UnknownVisionPreset:
        """Validate ALL trusted presets, then resolve exact caller-selected name.

        Every preset needs a nonblank string API key, even for offline extraction.
        Invalid credentials are a trusted configuration failure, not a provider
        outage or business rejection. Never use an environment/default key.
        Keys are passed unchanged only with the selected invocation target.
        """
        if not isinstance(self.presets, tuple) or not self.presets or any(
            not isinstance(preset, VisionPreset)
            or not all(isinstance(value, str) and value.strip() for value in (
                preset.name, preset.endpoint, preset.model, preset.api_key,
            ))
            for preset in self.presets
        ):
            raise InvalidModelPresetCatalogue("Invalid preset catalogue")
        if len({preset.name for preset in self.presets}) != len(self.presets):
            raise InvalidModelPresetCatalogue("Duplicate preset names")
        for preset in self.presets:
            try:
                endpoint = urlsplit(preset.endpoint)
                valid = (
                    endpoint.scheme in ("http", "https") and bool(endpoint.hostname)
                    and endpoint.username is None and endpoint.password is None
                )
            except ValueError:
                valid = False
            if not valid:
                raise InvalidModelPresetCatalogue("Invalid preset endpoint")
        for preset in self.presets:
            if preset.name == name:
                return preset
        return UnknownVisionPreset()
