"""Registration flow within IAM; expected decisions go to the Output Boundary.

Caller [deferred] -> RegisterInputBoundary -> RegisterInteractor
  -> Username / Email factories -> UserAccount.validate_password
  -> PasswordHasher.hash once [adapter deferred]
  -> UserIdGenerator.generate [adapter deferred]
  -> UserAccount.create (ACTIVE / version 0 / generation 0, non-admin here)
  -> UserRegistrationStore.create(account=Entity) [adapter deferred]
     -> GeneratedUserIdCollision with zero effects: regenerate/recreate, max 3 attempts
  -> RegisterOutputBoundary.present -> Presenter -> transport [deferred]
Success follows committed ACTIVE account creation, ready for separate login.
No token/session is issued here; Identity owns access state and generation.
Invalid input -> value object typed rejection -> present rejection.
Password matching username -> Entity-owned validation -> present invalid_password.
Undeclared password decision -> UnexpectedPasswordPolicyDecision -> outer handler.
Empty/non-string hash -> contract breach -> InvalidHashResult -> outer handler.
Unique identity conflict -> store adapter -> IdentityConflict result -> present rejection.
PasswordHashingError / UserIdGenerationError / other UserRegistrationError ->
adapter translation -> Interactor propagates -> outer handler [deferred], without
retry or a normal outcome. Exhausted ID collision recovery -> UserRegistrationError
-> outer handler without outcome. InvalidGeneratedUserIdResult,
InvalidRegisteredUserResult, unexpected domain/port results and unexpected failures
also reach that handler. Username/email rejection or success ends recovery;
presentation cannot roll back creation and never triggers another write.
"""

from datetime import datetime
from typing import Final

from contexts.iam.domain.identity.user_account import UserAccount, InvalidUserAccount
from contexts.iam.domain.identity.username import InvalidUsernameValue, Username
from contexts.iam.domain.identity.value_objects import Email, InvalidRegistrationValue, Password
from contexts.iam.application.modules.credentials.ports import InvalidHashResult, PasswordHasher
from contexts.iam.application.modules.registration.ports import (
    GeneratedUserIdCollision, IdentityConflict, InvalidGeneratedUserIdResult,
    InvalidIdentityConflictResult, InvalidRegisteredUserResult,
    RegisteredUser, UserIdGenerator, UserRegistrationError, UserRegistrationStore,
)

from .errors import UnexpectedAccountCreationResult, UnexpectedPasswordPolicyDecision
from .input_boundary import RegisterInputBoundary
from .output_boundary import RegisterOutputBoundary
from .request import RegisterRequest
from .response import RegistrationFailure, RegistrationSuccess


MAX_ACCOUNT_CREATION_ATTEMPTS: Final[int] = 3


class RegisterInteractor(RegisterInputBoundary):
    def __init__(
        self, hasher: PasswordHasher, identities: UserIdGenerator,
        users: UserRegistrationStore,
        output: RegisterOutputBoundary,
    ) -> None:
        self._hasher = hasher
        self._identities = identities
        self._users = users
        self._output = output

    def execute(self, request: RegisterRequest) -> None:
        username = Username.from_input(request.username)
        if isinstance(username, InvalidUsernameValue):
            self._output.present(RegistrationFailure(code=username.code))
            return
        email = Email.from_input(request.email)
        if isinstance(email, InvalidRegistrationValue):
            self._output.present(RegistrationFailure(code=email.code))
            return
        password = UserAccount.validate_password(username=username, raw=request.password)
        if isinstance(password, InvalidRegistrationValue):
            self._output.present(RegistrationFailure(code=password.code))
            return

        if not isinstance(password, Password):
            raise UnexpectedPasswordPolicyDecision("Undeclared account password decision")

        # Hash only after validation; neither result nor store ever sees plaintext.
        password_hash = self._hasher.hash(password.value)
        if not isinstance(password_hash, str):
            raise InvalidHashResult("Password hasher returned a non-string result")
        if password_hash == "":
            raise InvalidHashResult("empty password hash")
        for _ in range(MAX_ACCOUNT_CREATION_ATTEMPTS):
            account = UserAccount.create(
                user_id=self._identities.generate(), admin_eligible=False,
                username=username, email=email, password_hash=password_hash, password=password,
            )
            if isinstance(account, InvalidUserAccount) and account.field == "user_id":
                raise InvalidGeneratedUserIdResult("Identity generator returned invalid identity data")
            if isinstance(account, InvalidRegistrationValue):
                self._output.present(RegistrationFailure(code=account.code))
                return
            if not isinstance(account, UserAccount):
                raise UnexpectedAccountCreationResult("Entity factory returned invalid creation state")
            try:
                saved = self._users.create(account=account)
            except GeneratedUserIdCollision:
                continue
            break
        else:
            raise UserRegistrationError("Generated identity allocation exhausted")
        if isinstance(saved, IdentityConflict):
            if saved.field == "username":
                self._output.present(
                    RegistrationFailure(code="username_taken"))
                return
            if saved.field == "email":
                self._output.present(RegistrationFailure(code="email_taken"))
                return
            raise InvalidIdentityConflictResult("Undeclared identity conflict field")

        if not isinstance(saved, RegisteredUser):
            raise TypeError("Registration store returned an undeclared result")
        if (
            not isinstance(saved.user_id, str) or saved.user_id != account.user_id
            or not isinstance(saved.username, str) or saved.username != account.username.value
            or not isinstance(saved.email, str) or saved.email != account.email.value
        ):
            raise InvalidRegisteredUserResult("Registration store returned mismatched identity data")
        if not isinstance(saved.created_at, datetime) or saved.created_at.utcoffset() is None:
            raise InvalidRegisteredUserResult("Registration store returned invalid creation time")

        self._output.present(RegistrationSuccess(
            user_id=saved.user_id,
            username=saved.username,
            email=saved.email,
            created_at=saved.created_at,
        ))
