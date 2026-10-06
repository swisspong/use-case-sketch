"""Presentation contract owned by the login use case; adapter deferred."""

from typing import Protocol

from .response import LoginResult


class LoginOutputBoundary(Protocol):
    def present(self, result: LoginResult) -> None:
        """Deliver one final semantic outcome; formatting belongs to the Presenter."""
        ...
