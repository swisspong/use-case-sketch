"""System failures translated by adapters; never presentation messages."""


class PdfExtractionError(RuntimeError):
    """Recognized parser resource/technical failure; propagate without saving."""


class FallbackExtractionError(RuntimeError):
    """Recognized rendering/provider failure; recover this page as unavailable.

    Rendering failure, timeout or provider outage -> adapter -> this exception ->
    Interactor -> domain failed page -> save partial results -> deferred Presenter.
    Unexpected errors/contract breaches are NOT recoverable through this exception.
    """


class DocumentStorageError(RuntimeError):
    """Recognized persistence/acknowledgement failure; no success outcome/retry."""


class InvalidExtractionConfiguration(RuntimeError):
    """Invalid trusted server config, not an ordinary upload rejection."""


class InvalidPdfExtractionResult(RuntimeError):
    """Parser returned undeclared or malformed trusted facts."""


class InvalidFallbackExtractionResult(RuntimeError):
    """Fallback returned undeclared facts or an invalid domain transition."""


class InvalidStorageResult(RuntimeError):
    """Storage supplied a malformed acknowledgement; never emit success/retry."""
