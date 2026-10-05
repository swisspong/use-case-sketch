from typing import Protocol

from .response import ChangePasswordResult


class ChangePasswordOutputBoundary(Protocol):
    def present(self, result: ChangePasswordResult) -> None:
        """Deliver one semantic outcome, never plaintext, hashes or raw failures.

        Concrete Presenter, display text and transport mapping remain deferred.
        Presenter failures propagate and must never trigger another write.
        """
        ...
