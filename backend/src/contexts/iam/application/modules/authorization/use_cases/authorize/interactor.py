"""Authorization sketch inside IAM; no production integration.

Caller / Controller [deferred] -> AuthorizeInputBoundary -> AuthorizeInteractor
  -> AccessValidator.validate -> verified credential [adapter deferred]
  -> AccessAccountStore.protect(credential, unchanged token) [adapter deferred]
     -> protected authoritative UserAccount / None
     -> UserAccount.credential_eligibility(original credential generation) -> branch
     -> allowed: current account admin eligibility / trusted access requirement
  -> successful scope exit (no implicit commit; never suppress errors)
  -> AuthorizeOutputBoundary.present -> Presenter -> ViewModel / transport [deferred]
Technical credential rejection, missing account or domain credential denial ->
unauthenticated. Eligible non-admin requesting ADMIN -> forbidden. Normal execution
emits once; scoped outcomes emit only after successful exit. AccessValidationError,
contract breaches and unexpected failures -> outer error handler [deferred], without
outcome/retry. Resource-specific authorization and atomic mutations belong to their
owning use cases. Actual protection/freshness/barrier enforcement remains deferred.
"""

from contexts.iam.domain.identity.user_account import CredentialEligibility, UserAccount

from ...ports import (
    AccessAccountStore, AccessValidator, UnauthenticatedAccess, VerifiedCredential,
)

from .errors import InvalidAccessRequirement, InvalidAccessValidationResult
from .input_boundary import AuthorizeInputBoundary
from .output_boundary import AuthorizeOutputBoundary
from .request import AccessRequirement, AuthorizeRequest
from .response import AuthorizeFailure, AuthorizeResult, AuthorizeSuccess


class AuthorizeInteractor(AuthorizeInputBoundary):
    def __init__(
        self, access: AccessValidator, output: AuthorizeOutputBoundary,
        *, accounts: AccessAccountStore,
    ) -> None:
        self._accounts = accounts
        self._access = access
        self._output = output

    def execute(
        self, request: AuthorizeRequest, *, requirement: AccessRequirement,
    ) -> None:
        if not isinstance(requirement, AccessRequirement):
            raise InvalidAccessRequirement("Caller must select an AccessRequirement")
        if not isinstance(request.token, str) or not request.token.strip():
            self._output.present(AuthorizeFailure(code="unauthenticated"))
            return
        credential = self._access.validate(request.token)
        if isinstance(credential, UnauthenticatedAccess):
            self._output.present(AuthorizeFailure(code="unauthenticated"))
            return
        if not isinstance(credential, VerifiedCredential):
            raise InvalidAccessValidationResult("Access validator returned an undeclared result")
        if (
            not isinstance(credential.actor_id, str) or not credential.actor_id.strip()
            or (
                credential.credential_generation is not None
                and type(credential.credential_generation) is not int
            )
        ):
            raise InvalidAccessValidationResult("Access validator returned invalid verification facts")
        outcome: AuthorizeResult
        with self._accounts.protect(credential=credential, token=request.token) as account:
            if account is None:
                outcome = AuthorizeFailure(code="unauthenticated")
            else:
                if not isinstance(account, UserAccount) or account.user_id != credential.actor_id:
                    raise InvalidAccessValidationResult("Scope returned invalid or mismatched account facts")
                decision = account.credential_eligibility(generation=credential.credential_generation)
                if decision is CredentialEligibility.DENIED:
                    outcome = AuthorizeFailure(code="unauthenticated")
                elif decision is CredentialEligibility.ALLOWED:
                    if requirement is AccessRequirement.ADMIN and not account.admin_eligible:
                        outcome = AuthorizeFailure(code="forbidden")
                    else:
                        outcome = AuthorizeSuccess(actor_id=account.user_id)
                else:
                    raise InvalidAccessValidationResult("Undeclared account credential decision")
        self._output.present(outcome)
