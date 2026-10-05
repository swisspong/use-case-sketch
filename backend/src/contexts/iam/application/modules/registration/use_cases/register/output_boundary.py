"""Presentation contract owned by the register use case; adapter deferred."""

from typing import Protocol

from .response import RegisterResult


class RegisterOutputBoundary(Protocol):
    def present(self, result: RegisterResult) -> None:
        """Deliver one final semantic outcome; formatting belongs to the Presenter."""
        ...
