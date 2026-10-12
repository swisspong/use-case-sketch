"""Trusted server configuration, NOT fields accepted by the upload request.

Extraction needs only quality thresholds. Model presets/credentials belong to
the separate, deferred OCR use case and are never read by extraction.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractionConfig:
    # Problem-character percentage strictly above this suggests OCR.
    unreadable_threshold_percent: float = 60.0
    # Explicit opt-in: omitted/null CLI config maps to None (not assessed).
    # A finite percentage in [0, 100] enables reports; validated by the domain.
    suspicious_threshold_percent: float | None = None
