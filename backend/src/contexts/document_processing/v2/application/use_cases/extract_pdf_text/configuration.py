"""Trusted server configuration, NOT fields accepted by the upload request.

The deferred admin configuration interface owns preset editing and admin
access control. Uploads select only by approved preset name; this application
resolves the exact endpoint/model. There is no implicit default preset and the
upload caller cannot supply arbitrary URLs or model names.
Presets are administrator-approved (name, endpoint, model, api_key) combinations.
The shared catalogue requires a nonblank string key on EVERY preset, including
local-offline, before dependency I/O. A missing/blank/non-string key becomes
InvalidExtractionConfiguration -> outer handler, never fallback_unavailable.
No environment-key fallback. Pass only the selected preset's exact key to the
model port; never copy credentials into domain state, storage or outcomes.
Preset/config repr hides keys; do not serialize or log the trusted config itself.
Endpoint/network allowlisting and actual model capability checks remain deferred.
"""

from dataclasses import dataclass

from ...model_presets import (
    InvalidModelPresetCatalogue, ModelPresetCatalogue, UnknownVisionPreset, VisionPreset,
)
from .errors import InvalidExtractionConfiguration

# Keep existing imports and ExtractionConfig's exception contract compatible.
__all__ = ["ExtractionConfig", "UnknownVisionPreset", "VisionPreset"]


@dataclass(frozen=True)
class ExtractionConfig:
    presets: tuple[VisionPreset, ...]
    unreadable_threshold_percent: float = 60.0
    # Explicit opt-in: omitted/null CLI config maps to None (not assessed).
    # A finite percentage in [0, 100] enables reports; validated by the domain.
    suspicious_threshold_percent: float | None = None

    def select(self, name: str) -> VisionPreset | UnknownVisionPreset:
        """Delegate shared lookup, preserving the existing configuration failure type."""
        try:
            return ModelPresetCatalogue(self.presets).select(name)
        except InvalidModelPresetCatalogue as error:
            raise InvalidExtractionConfiguration(str(error)) from None
