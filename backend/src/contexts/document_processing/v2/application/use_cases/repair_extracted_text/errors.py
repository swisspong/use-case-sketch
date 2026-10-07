"""Application-owned system failures; adapters never expose provider messages."""


class RepairSourceError(RuntimeError):
    """Known source read/storage failure -> source adapter -> outer handler.

    No LLM invocation, presentation or retry. Missing document/page is instead
    the typed RepairPageNotFound result, not this exception.
    """


class TextRepairError(RuntimeError):
    """Known provider/network/resource failure -> text adapter -> outer handler.

    No recovery, success presentation or automatic retry. Unexpected errors propagate.
    """


class RepairRunStorageError(RuntimeError):
    """History storage/read failure; no success, retry or assumed rollback."""


class InvalidRepairSourceResult(RuntimeError):
    """Malformed/undeclared source facts -> Interactor -> outer handler."""


class InvalidTextRepairResult(RuntimeError):
    """Malformed/undeclared trusted model result, not an ordinary rejection."""
