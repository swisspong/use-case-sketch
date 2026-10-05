from typing import Protocol

from .request import LoginRequest


class LoginInputBoundary(Protocol):
    def execute(self, request: LoginRequest) -> None:
        """Authenticate and emit one terminal semantic outcome via the output port.

        Lookup returns full UserAccount facts, including suspended accounts; the
        Interactor calls login_eligibility(admin_required=False). Invalid username,
        missing/ineligible account or password mismatch -> invalid_credentials.
        Missing/ineligible lookup uses dummy password verification.
        After password verification, protect current account facts through local
        credential_eligibility with the ORIGINAL lookup generation and technical
        TokenIssuer issuance. Missing/current denial -> invalid_credentials before
        issuance. Never upgrade a stale snapshot, retry rejection or let an adapter
        execute local business decisions. Issue using the shared application TTL
        of 15 minutes, not request input or an independent adapter default.
        Scoped success/rejection presents only after successful exit. Known lookup,
        verification, scope or issuance failures and contract breaches reach the
        deferred outer handler with no normal outcome/retry. Issuance cannot be
        rolled back by exit/presentation failure. No second returned result.
        Production protection, expiry and barrier enforcement remain deferred;
        mocked unit tests cannot prove these technical guarantees.
        """
        ...
