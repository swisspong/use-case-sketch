from typing import Protocol

from .request import AdminLoginRequest


class AdminLoginInputBoundary(Protocol):
    def execute(self, request: AdminLoginRequest) -> None:
        """Authenticate an admin and emit one terminal outcome via the output port.

        Lookup returns full UserAccount facts, including non-admin/suspended users;
        the Interactor calls login_eligibility(admin_required=True). Invalid username,
        missing/ineligible account or password mismatch -> invalid_credentials.
        Missing/ineligible lookup uses dummy password verification. Admin eligibility
        is the authoritative lookup snapshot guarantee, not a client role or an
        atomic issuance-role check; resource authorization reads current eligibility.
        After password verification, protect current account facts through the
        Interactor's credential_eligibility using the ORIGINAL lookup generation
        and technical token issuance. Missing/current denial -> invalid_credentials
        before issuance. Never upgrade snapshots, retry rejection or delegate local
        eligibility decisions to adapters. TTL is the shared application-selected
        15 minutes, not request input or an independent adapter default.
        Scoped success/rejection presents only after successful exit. Dependency
        failures and contract breaches reach the deferred outer handler without
        outcome/retry. Exit/presentation failure cannot undo completed issuance.
        No second returned result. Production protection, expiry and barriers remain
        deferred and unproved by application mocks.
        """
        ...
