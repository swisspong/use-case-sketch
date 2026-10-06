"""Application-owned output contract; concrete Presenter is deferred."""

from typing import Protocol

from .response import ChangeUserStatusResult


class ChangeUserStatusOutputBoundary(Protocol):
    def present(self, result: ChangeUserStatusResult) -> None:
        """Deliver one final semantic outcome without credentials or failure text.

        Display text, localization and transport mapping belong to the Presenter.
        Presenter failures propagate; presentation and persistence are not atomic.
        """
        ...
