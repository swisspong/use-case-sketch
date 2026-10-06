"""Application-owned presentation contract; concrete Presenter deferred."""

from typing import Protocol

from .response import AdminLoginResult


class AdminLoginOutputBoundary(Protocol):
    def present(self, result: AdminLoginResult) -> None:
        """Deliver one terminal outcome, never passwords, hashes or failure text.

        Display text, localization and transport status belong to the deferred
        Presenter. Token delivery is sensitive and must not be logged. Presenter
        failures propagate; token issuance and delivery are not atomic or retried.
        """
        ...
