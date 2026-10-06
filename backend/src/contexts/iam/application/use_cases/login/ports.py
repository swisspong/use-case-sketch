"""Account lookup owned by IAM's login use case; production adapter deferred.

AccountLookupError and InvalidLoginAccountResult are shared lookup failures owned
by application.authentication_ports, with the same meaning for login/admin_login.
"""

from typing import Protocol

from contexts.iam.domain.identity.user_account import UserAccount


class LoginAccountStore(Protocol):
    def find_by_username(self, username: str) -> UserAccount | None:
        """Read the full authoritative account bound to the canonical username.

        Return suspended accounts too; only missing is None. Rehydrate using
        UserAccount.from_persisted, preserving all recorded facts in one consistent
        snapshot. Do not normalize corruption or execute/filter login eligibility.
        The Interactor calls login_eligibility(admin_required=False), then branches.
        Missing/denied -> Interactor dummy verification -> invalid_credentials ->
        deferred Presenter. This snapshot is not a later issuance grant.
        InvalidUserAccount while loading or recognized storage/corruption failure
        -> adapter -> AccountLookupError -> outer handler, no outcome/retry.
        Leaked factory rejection/mismatched username -> Interactor ->
        InvalidLoginAccountResult; undeclared result -> TypeError -> outer handler
        before verification/issuance/presentation. Unexpected errors propagate.
        Never expose hashes/secrets. Production snapshot guarantees deferred.
        """
        ...
