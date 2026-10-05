"""IAM self-service password change; production integration remains deferred.

Caller / Controller [deferred] supplies trusted actor_id
  -> ChangePasswordInputBoundary -> ChangePasswordInteractor
     -> PasswordAccountStore.load(UserAccount) [production adapter deferred]
     -> UserAccount.permits_password_change
     -> PasswordVerifier.verify(current secret, Entity hash) [adapter deferred]
     -> UserAccount.validate_password -> Password / typed rejection
     -> use-case-specific distinct-current-password decision
     -> PasswordHasher.hash(validated candidate) [adapter deferred]
     -> UserAccount.change_password -> UserAccountTransition / typed rejection
     -> PasswordAccountStore.commit(exact transition) [adapter deferred]
     -> ChangePasswordOutputBoundary.present
        -> Presenter -> ViewModel / transport output [deferred]
Missing/inactive account -> unauthenticated; wrong current secret ->
invalid_current_password; invalid candidate -> invalid_new_password; same secret ->
password_unchanged; stale commit -> password_conflict. Normal branches emit once.
UserAccount owns ACTIVE-only rotation across ALL password-change channels and
advances revision/generation once, preserving identity/status/admin eligibility.
Both ordinary users and admins may change only their own passwords. No token is
issued; the supplied transition commits with invalidation of all old credentials.
Known store/verifier/hasher failures -> respective adapters -> PasswordStoreError /
PasswordVerificationError / PasswordHashingError -> outer handler [deferred], with
no outcome/retry. Undeclared/wrong-identity store results -> InvalidPasswordStoreResult;
non-bool verifier -> InvalidPasswordVerificationResult; invalid hash -> InvalidHashResult;
undeclared inner decisions -> UnexpectedPasswordChangeDecision. These and unexpected
failures also reach the handler. Presentation cannot roll back a commit or retry it.
Mocks do not prove production atomicity, races, actual hash correctness or barriers.
Identity owns account values; the credentials module owns shared password ports.
"""

from contexts.iam.application.modules.credentials.ports import (
    InvalidHashResult, InvalidPasswordVerificationResult, PasswordHasher, PasswordVerifier,
)
from contexts.iam.application.modules.user_management.password_ports import (
    InvalidPasswordStoreResult, PasswordAccountStore, PasswordAccountUnavailable,
    PasswordChanged, PasswordChangeConflict,
)
from contexts.iam.domain.identity.user_account import (
    InvalidPasswordChange, PasswordChangeRejection, UserAccountTransition, UserAccount,
)
from contexts.iam.domain.identity.value_objects import InvalidRegistrationValue, Password

from .errors import UnexpectedPasswordChangeDecision
from .input_boundary import ChangePasswordInputBoundary
from .output_boundary import ChangePasswordOutputBoundary
from .request import ChangePasswordRequest
from .response import ChangePasswordFailure, ChangePasswordSuccess


class ChangePasswordInteractor(ChangePasswordInputBoundary):
    def __init__(
        self, accounts: PasswordAccountStore, verifier: PasswordVerifier,
        hasher: PasswordHasher, output: ChangePasswordOutputBoundary,
    ) -> None:
        self._accounts = accounts
        self._verifier = verifier
        self._hasher = hasher
        self._output = output

    def execute(self, request: ChangePasswordRequest, *, actor_id: str) -> None:
        account = self._accounts.load(actor_id=actor_id)
        if isinstance(account, PasswordAccountUnavailable):
            self._output.present(ChangePasswordFailure("unauthenticated"))
            return
        if not isinstance(account, UserAccount):
            raise InvalidPasswordStoreResult("Undeclared password account snapshot")
        if account.user_id != actor_id:
            raise InvalidPasswordStoreResult("Password account belongs to another identity")
        if not account.permits_password_change():
            self._output.present(ChangePasswordFailure("unauthenticated"))
            return
        verified = self._verifier.verify(request.current_password, account.password_hash)
        if verified is False:
            self._output.present(ChangePasswordFailure("invalid_current_password"))
            return
        if verified is not True:
            raise InvalidPasswordVerificationResult("Password verifier returned a non-bool result")
        password = account.validate_password(username=account.username, raw=request.new_password)
        if isinstance(password, InvalidRegistrationValue):
            self._output.present(ChangePasswordFailure("invalid_new_password"))
            return
        if not isinstance(password, Password):
            raise UnexpectedPasswordChangeDecision("Undeclared account password decision")
        # This distinct-current-password rule is self-service-specific.
        if password.value == request.current_password:
            self._output.present(ChangePasswordFailure("password_unchanged"))
            return
        password_hash = self._hasher.hash(password.value)
        if not isinstance(password_hash, str) or not password_hash:
            raise InvalidHashResult("Password hasher returned invalid hash data")
        transition = account.change_password(
            password=password, password_hash=password_hash, expected_version=account.version,
        )
        # These domain branches are defensive: this immutable snapshot was already
        # checked and its exact revision/candidate supplied. Persistence races are
        # reported separately by commit, never by upgrading the snapshot here.
        if transition is PasswordChangeRejection.INACTIVE:
            self._output.present(ChangePasswordFailure("unauthenticated"))
            return
        if transition is PasswordChangeRejection.VERSION_CONFLICT:
            self._output.present(ChangePasswordFailure("password_conflict"))
            return
        if isinstance(transition, InvalidRegistrationValue):
            self._output.present(ChangePasswordFailure("invalid_new_password"))
            return
        if isinstance(transition, InvalidPasswordChange):
            raise UnexpectedPasswordChangeDecision("Validated password transition arguments rejected")
        if not isinstance(transition, UserAccountTransition):
            raise UnexpectedPasswordChangeDecision("Undeclared account password transition")
        result = self._accounts.commit(transition=transition)
        if isinstance(result, PasswordAccountUnavailable):
            self._output.present(ChangePasswordFailure("unauthenticated"))
            return
        if isinstance(result, PasswordChangeConflict):
            self._output.present(ChangePasswordFailure("password_conflict"))
            return
        if not isinstance(result, PasswordChanged):
            raise InvalidPasswordStoreResult("Password store returned an undeclared commit result")
        self._output.present(ChangePasswordSuccess())
