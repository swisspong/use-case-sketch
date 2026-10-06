"""Trusted server configuration, NOT fields accepted by the upload request.

The deferred admin configuration interface owns preset editing and admin
access control. Uploads select only by approved preset name; this application
resolves the exact endpoint/model. There is no implicit default preset and the
upload caller cannot supply arbitrary URLs or model names.
Presets are administrator-approved (name, endpoint, model) combinations. Credentials
must be injected into the deferred adapter, never included here or in outcomes.
Endpoint/network allowlisting and actual model capability checks remain deferred.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from .errors import InvalidExtractionConfiguration


@dataclass(frozen=True)
class VisionPreset:
    name: str
    endpoint: str
    model: str


@dataclass(frozen=True)
class UnknownVisionPreset:
    """An upload selected a name not in the administrator-approved catalogue."""


@dataclass(frozen=True)
class ExtractionConfig:
    presets: tuple[VisionPreset, ...]
    unreadable_threshold_percent: float = 60.0
    # Explicit opt-in: omitted/null CLI config maps to None (not assessed).
    # A finite percentage in [0, 100] enables reports; validated by the domain.
    suspicious_threshold_percent: float | None = None

    def select(self, name: str) -> VisionPreset | UnknownVisionPreset:
        """Exact name lookup; never take an upload-supplied URL or model string."""
        if not isinstance(self.presets, tuple) or not self.presets or any(
            not isinstance(preset, VisionPreset)
            or not all(isinstance(value, str) and value.strip() for value in (
                preset.name, preset.endpoint, preset.model,
            ))
            for preset in self.presets
        ):
            raise InvalidExtractionConfiguration("Invalid preset catalogue")
        if len({preset.name for preset in self.presets}) != len(self.presets):
            raise InvalidExtractionConfiguration("Duplicate preset names")
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
                raise InvalidExtractionConfiguration("Invalid preset endpoint")
        for preset in self.presets:
            if preset.name == name:
                return preset
        return UnknownVisionPreset()
