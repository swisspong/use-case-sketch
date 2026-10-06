"""Account lookup owned by IAM's admin_login use case; adapter deferred.

AccountLookupError and InvalidLoginAccountResult are shared lookup failures owned
by application.authentication_ports, with the same meaning for login/admin_login.
"""

from typing import Protocol

from contexts.iam.domain.identity.user_account import UserAccount


class AdminLoginAccountStore(Protocol):
    def find_admin_by_username(self, username: str) -> UserAccount | None:
        """Read facts for admin_login, without filtering non-admin/suspended users.

        The historical name identifies its consumer, not a permission grant.
        Return the full UserAccount for the exact canonical username; missing is
        None. Rehydrate recorded state from one consistent authoritative snapshot.
        The Interactor calls login_eligibility(admin_required=True), never the
        adapter. Missing/non-admin/suspended -> dummy verification ->
        invalid_credentials -> deferred Presenter. Eligibility comes from trusted
        account data, never a reserved username or client-supplied role.
        InvalidUserAccount while loading or known storage/corruption failure ->
        adapter -> AccountLookupError -> outer handler without outcome/retry.
        Leaked factory rejection/mismatched username -> Interactor ->
        InvalidLoginAccountResult; undeclared result -> TypeError -> outer handler
        before verification/issuance/presentation. Unexpected errors propagate.
        Lookup approval is preliminary: admin_login must recheck the Entity's
        ACTIVE-admin rule inside LoginGrantStore's protected issuance scope.
        Subsequent authorization also checks current eligibility. Production
        adapters and snapshot/protection tests remain deferred.
        """
        ...
