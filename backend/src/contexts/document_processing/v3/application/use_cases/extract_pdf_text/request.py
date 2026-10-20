from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractPdfTextRequest:
    """Uploaded PDF only; no model/preset/threshold/permissions."""

    pdf: bytes = field(repr=False)
