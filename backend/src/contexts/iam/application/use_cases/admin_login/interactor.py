"""IAM admin login; account decisions execute here, not in deferred adapters.

Caller / Controller [deferred] -> AdminLoginInputBoundary -> AdminLoginInteractor
  -> Username.from_input
  -> AdminLoginAccountStore.find_admin_by_username -> UserAccount [adapter deferred]
  -> UserAccount.login_eligibility(admin_required=True) -> branch
  -> PasswordVerifier.verify / verify_missing [adapter deferred]
  -> LoginGrantStore.protect(verified identity) [adapter deferred]
     -> protected current UserAccount / None
     -> UserAccount.administrative_eligibility(current ACTIVE admin) -> branch
     -> UserAccount.credential_eligibility(original lookup generation) -> branch
     -> allowed: TokenIssuer.issue(identity, original generation, TTL) [adapter deferred]
  -> successful scope exit (no implicit commit; never suppress errors)
  -> AdminLoginOutputBoundary.present -> Presenter -> ViewModel / transport [deferred]
Missing/non-admin/inactive lookup, password mismatch or current credential denial
-> invalid_credentials -> output once. Scoped decisions present after exit only.
Lookup approval is preliminary. The Entity's shared ACTIVE-admin rule executes
again inside the issuance scope; role revocation serializes with issuance even
without a generation change. Later resource authorization also checks current
eligibility. Lookup guards -> InvalidLoginAccountResult / TypeError;
scope guards -> InvalidLoginGrantResult; verifier/issuer guards ->
InvalidPasswordVerificationResult / InvalidTokenIssuanceResult. These, adapter-translated
AccountLookupError / PasswordVerificationError / LoginGrantError / TokenIssuanceError
and unexpected failures -> outer error handler [deferred], no outcome/retry.
Original generation and application-selected 15-minute TTL are unchanged.
Completed issuance cannot be rolled back by exit/presentation failure. Production
protection, expiry/barriers, rate-limiting, MFA and resource authorization deferred.
"""

from contexts.iam.domain.identity.username import InvalidUsernameValue, Username
from contexts.iam.domain.identity.user_account import (
    AdministrativeEligibility, CredentialEligibility, InvalidUserAccount,
    LoginEligibility, UserAccount,
)

from contexts.iam.application.password_ports import (
    InvalidPasswordVerificationResult, PasswordVerifier,
)

from ...authentication_ports import (
    InvalidLoginAccountResult, IssuedToken,
    InvalidLoginGrantResult, InvalidTokenIssuanceResult, LoginGrantStore, TokenIssuer,
)
from ...login_token_policy import LOGIN_ACCESS_TOKEN_TTL
from .ports import AdminLoginAccountStore
from .input_boundary import AdminLoginInputBoundary
from .output_boundary import AdminLoginOutputBoundary
from .request import AdminLoginRequest
from .response import AdminLoginFailure, AdminLoginResult, AdminLoginSuccess


class AdminLoginInteractor(AdminLoginInputBoundary):
    def __init__(
        self,
        accounts: AdminLoginAccountStore,
        passwords: PasswordVerifier,
        tokens: TokenIssuer,
        output: AdminLoginOutputBoundary,
        *, grants: LoginGrantStore,
    ) -> None:
        self._grants = grants
        self._accounts = accounts
        self._passwords = passwords
        self._tokens = tokens
        self._output = output

    def execute(self, request: AdminLoginRequest) -> None:
        username = Username.from_input(request.username)
        if isinstance(username, InvalidUsernameValue):
            self._passwords.verify_missing(request.password)
            self._output.present(AdminLoginFailure(code="invalid_credentials"))
            return
        account = self._accounts.find_admin_by_username(username.value)
        if account is None:
            self._passwords.verify_missing(request.password)
            self._output.present(AdminLoginFailure(code="invalid_credentials"))
            return
        if isinstance(account, InvalidUserAccount):
            raise InvalidLoginAccountResult("Account store leaked invalid persisted facts")
        if not isinstance(account, UserAccount):
            raise TypeError("Admin account store returned an undeclared result")
        if account.username.value != username.value:
            raise InvalidLoginAccountResult("Account store returned a mismatched username")
        eligibility = account.login_eligibility(admin_required=True)
        if eligibility is LoginEligibility.DENIED:
            self._passwords.verify_missing(request.password)
            self._output.present(AdminLoginFailure(code="invalid_credentials"))
            return
        if eligibility is not LoginEligibility.ALLOWED:
            raise InvalidLoginAccountResult("Undeclared account login decision")
        verified = self._passwords.verify(request.password, account.password_hash)
        if type(verified) is not bool:
            raise InvalidPasswordVerificationResult("Password verifier returned a non-bool result")
        if verified is False:
            self._output.present(AdminLoginFailure(code="invalid_credentials"))
            return
        outcome: AdminLoginResult
        with self._grants.protect(user_id=account.user_id) as current:
            if current is None:
                outcome = AdminLoginFailure(code="invalid_credentials")
            else:
                if not isinstance(current, UserAccount) or current.user_id != account.user_id:
                    raise InvalidLoginGrantResult("Scope returned invalid or mismatched account facts")
                admin_eligibility = current.administrative_eligibility()
                if admin_eligibility is AdministrativeEligibility.DENIED:
                    outcome = AdminLoginFailure(code="invalid_credentials")
                elif admin_eligibility is AdministrativeEligibility.ALLOWED:
                    grant_eligibility = current.credential_eligibility(
                        generation=account.credential_generation,
                    )
                    if grant_eligibility is CredentialEligibility.DENIED:
                        outcome = AdminLoginFailure(code="invalid_credentials")
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
                        outcome = AdminLoginSuccess(token=issued.token)
                    else:
                        raise InvalidLoginGrantResult("Undeclared account credential decision")
                else:
                    raise InvalidLoginGrantResult("Undeclared account administrative decision")
        self._output.present(outcome)
