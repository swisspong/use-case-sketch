from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractPdfTextRequest:
    """Uploaded PDF and approved preset name; no URL/model/threshold/permissions."""

    pdf: bytes = field(repr=False)
    preset_name: str
