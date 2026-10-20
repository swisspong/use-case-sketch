"""System failures translated by adapters; never presentation messages."""


class PdfExtractionError(RuntimeError):
    """Recognized parser resource/technical failure; propagate without saving."""


class DocumentStorageError(RuntimeError):
    """Recognized persistence/acknowledgement failure; no success outcome/retry."""


class InvalidExtractionConfiguration(RuntimeError):
    """Invalid trusted server config, not an ordinary upload rejection."""


class InvalidPdfExtractionResult(RuntimeError):
    """Parser returned undeclared or malformed trusted facts."""


class InvalidStorageResult(RuntimeError):
    """Storage supplied a malformed acknowledgement; never emit success/retry."""
