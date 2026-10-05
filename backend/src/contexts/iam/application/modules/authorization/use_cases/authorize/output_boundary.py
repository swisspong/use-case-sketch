"""Application-owned output contract; concrete Presenter deferred."""

from typing import Protocol

from .response import AuthorizeResult


class AuthorizeOutputBoundary(Protocol):
    def present(self, result: AuthorizeResult) -> None:
        """Emit one final semantic outcome, never the submitted token or secrets.

        Display text, localization and transport mapping belong to the deferred
        Presenter. Presentation failures propagate to the outer handler; no retry.
        """
        ...
