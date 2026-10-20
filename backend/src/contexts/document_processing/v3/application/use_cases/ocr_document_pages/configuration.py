"""Trusted server configuration for OCR; never supplied by the request.

OCR text is validated with the threshold_percent saved with the document's
extraction, not a threshold from this configuration.
"""

from dataclasses import dataclass

from ...model_presets import VisionPreset


@dataclass(frozen=True)
class OcrConfig:
    presets: tuple[VisionPreset, ...]
