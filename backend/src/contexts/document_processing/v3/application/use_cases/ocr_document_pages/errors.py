"""System failures translated by adapters; never presentation messages."""


class InvalidOcrConfiguration(RuntimeError):
    """Invalid trusted preset catalogue/threshold -> outer handler before any I/O."""


class DocumentSourceError(RuntimeError):
    """Saved document/PDF could not be read (I/O, corrupt record) -> outer handler."""


class PageRenderingError(RuntimeError):
    """Recognized rasterization failure for one page (pypdfium2 adapter)."""


class OcrProviderError(RuntimeError):
    """Recognized provider failure: timeout, outage, auth, rate limit, malformed or
    truncated reply (OpenAICompatibleOcrReader).

    Provider messages/credentials never appear in this exception's message.
    """


class OcrAttemptStorageError(RuntimeError):
    """Recognized append/ack failure; may follow a real commit; never retry."""


class InvalidOcrResult(RuntimeError):
    """A port returned undeclared/malformed facts; never a business outcome."""
