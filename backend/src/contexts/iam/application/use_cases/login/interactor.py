"""IAM login; account decisions execute here, not in deferred adapters.

Caller / Controller [deferred] -> LoginInputBoundary -> LoginInteractor
  -> Username.from_input
  -> LoginAccountStore.find_by_username -> full UserAccount [adapter deferred]
  -> UserAccount.login_eligibility(admin_required=False) -> branch
  -> PasswordVerifier.verify / verify_missing [adapter deferred]
  -> LoginGrantStore.protect(verified identity) [adapter deferred]
     -> protected current UserAccount / None
     -> UserAccount.credential_eligibility(original lookup generation) -> branch
     -> allowed: TokenIssuer.issue(identity, original generation, TTL) [adapter deferred]
  -> successful scope exit (no implicit commit; never suppress errors)
  -> LoginOutputBoundary.present -> Presenter -> ViewModel / transport [deferred]
Missing/ineligible lookup, password mismatch or current credential denial ->
invalid_credentials -> output once. Issuance and scoped rejection present only
AFTER successful exit. Lookup guards -> InvalidLoginAccountResult / TypeError;
scope guards -> InvalidLoginGrantResult; verifier/issuer guards ->
InvalidPasswordVerificationResult / InvalidTokenIssuanceResult. These, adapter-translated
AccountLookupError / PasswordVerificationError / LoginGrantError / TokenIssuanceError
and unexpected failures -> outer error handler [deferred], no outcome/retry.
UserAccount owns ACTIVE/admin/current-generation rules. Application selects the
15-minute TTL and preserves the password-verified snapshot generation; no upgrade.
Completed remote issuance cannot be rolled back by exit/presentation failure.
Production snapshots, scope protection, expiry and barrier enforcement deferred.
"""

from contexts.iam.domain.identity.username import InvalidUsernameValue, Username
from contexts.iam.domain.identity.user_account import (
    CredentialEligibility, InvalidUserAccount, LoginEligibility, UserAccount,
)

from contexts.iam.application.password_ports import (
    InvalidPasswordVerificationResult, PasswordVerifier,
)

from ...authentication_ports import (
    InvalidLoginAccountResult, IssuedToken, LoginGrantStore,
    InvalidLoginGrantResult, InvalidTokenIssuanceResult, TokenIssuer,
)
from ...login_token_policy import LOGIN_ACCESS_TOKEN_TTL
from .ports import LoginAccountStore
from .input_boundary import LoginInputBoundary
from .output_boundary import LoginOutputBoundary
from .request import LoginRequest
from .response import LoginFailure, LoginResult, LoginSuccess


class LoginInteractor(LoginInputBoundary):
    def __init__(
        self,
        accounts: LoginAccountStore,
        passwords: PasswordVerifier,
        tokens: TokenIssuer,
        output: LoginOutputBoundary,
        *, grants: LoginGrantStore,
    ) -> None:
        self._grants = grants
        self._accounts = accounts
        self._passwords = passwords
        self._tokens = tokens
        self._output = output

    def execute(self, request: LoginRequest) -> None:
        username = Username.from_input(request.username)
        if isinstance(username, InvalidUsernameValue):
            self._passwords.verify_missing(request.password)
            self._output.present(LoginFailure(code="invalid_credentials"))
            return
        account = self._accounts.find_by_username(username.value)
        if account is None:
            self._passwords.verify_missing(request.password)
            self._output.present(LoginFailure(code="invalid_credentials"))
            return
        if isinstance(account, InvalidUserAccount):
            raise InvalidLoginAccountResult("Account store leaked invalid persisted facts")
        if not isinstance(account, UserAccount):
            raise TypeError("Account store returned an undeclared result")
        if account.username.value != username.value:
            raise InvalidLoginAccountResult("Account store returned a mismatched username")
        eligibility = account.login_eligibility(admin_required=False)
        if eligibility is LoginEligibility.DENIED:
            self._passwords.verify_missing(request.password)
            self._output.present(LoginFailure(code="invalid_credentials"))
            return
        if eligibility is not LoginEligibility.ALLOWED:
            raise InvalidLoginAccountResult("Undeclared account login decision")
        verified = self._passwords.verify(request.password, account.password_hash)
        if type(verified) is not bool:
            raise InvalidPasswordVerificationResult("Password verifier returned a non-bool result")
        if verified is False:
            self._output.present(LoginFailure(code="invalid_credentials"))
            return
        outcome: LoginResult
        with self._grants.protect(user_id=account.user_id) as current:
            if current is None:
                outcome = LoginFailure(code="invalid_credentials")
            else:
                if not isinstance(current, UserAccount) or current.user_id != account.user_id:
                    raise InvalidLoginGrantResult("Scope returned invalid or mismatched account facts")
                grant_eligibility = current.credential_eligibility(
                    generation=account.credential_generation,
                )
                if grant_eligibility is CredentialEligibility.DENIED:
                    outcome = LoginFailure(code="invalid_credentials")
                elif grant_eligibility is CredentialEligibility.ALLOWED:
                    issued = self._tokens.issue(
                        user_id=account.user_id,
                        credential_generation=account.credential_generation,
                        ttl=LOGIN_ACCESS_TOKEN_TTL,
                    )
                    if not isinstance(issued, IssuedToken):
                        raise InvalidTokenIssuanceResult("Token issuer returned an undeclared result")
                    if not isinstance(issued.token, str) or not issued.token:
                        raise InvalidTokenIssuanceResult("Token issuer returned invalid token data")
                    outcome = LoginSuccess(token=issued.token)
                else:
                    raise InvalidLoginGrantResult("Undeclared account credential decision")
        self._output.present(outcome)
