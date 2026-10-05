"""IAM's immutable account Entity: sole identity, credential and access-state owner.

The same user_id survives password changes and suspension/restoration. Actor
permissions belong to policies; atomic persistence and barriers belong to ports.
Identity owns the shared Email/Password values; they are not another write model
or separate bounded context.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from .value_objects import (
    Email, InvalidRegistrationValue, Password,
)

from .user_access_status import UserAccessStatus
from .username import Username


@dataclass(frozen=True)
class InvalidUserAccount:
    """Factory rejection; adapters translate invalid persisted facts to system errors."""

    field: Literal[
        "user_id", "status", "version", "credential_generation", "admin_eligible",
        "username", "email", "password_hash", "password",
    ]


@dataclass(frozen=True)
class InvalidAccountAccessChange:
    field: Literal["status", "expected_version"]


class AccountAccessRejection(str, Enum):
    ADMIN_TARGET_FORBIDDEN = "admin_target_forbidden"
    VERSION_CONFLICT = "version_conflict"
    ALREADY_SET = "already_set"


class LoginEligibility(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"


class CredentialEligibility(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"


class InvalidAccountDecisionFacts(RuntimeError):
    """Malformed trusted facts/configuration or an undeclared inner decision."""


class PasswordChangeRejection(str, Enum):
    INACTIVE = "inactive"
    VERSION_CONFLICT = "version_conflict"


@dataclass(frozen=True)
class InvalidPasswordChange:
    field: Literal["password", "password_hash", "expected_version"]


@dataclass(frozen=True, init=False)
class UserAccount:
    user_id: str
    username: Username
    email: Email
    password_hash: str = field(repr=False)
    status: UserAccessStatus
    version: int
    credential_generation: int
    admin_eligible: bool

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("Use UserAccount.create or UserAccount.from_persisted")

    @classmethod
    def create(
        cls, *, user_id: str, admin_eligible: bool, username: Username,
        email: Email, password_hash: str, password: Password,
    ) -> "UserAccount | InvalidUserAccount | InvalidRegistrationValue[Literal['invalid_password']]":
        """Creation invariants: ACTIVE/version 0/generation 0, valid password.

        password is only validated, never retained. The trusted hashing port/caller
        binds password_hash to this exact candidate. Admin eligibility is a trusted
        choice; public registration selects False. Rehydration needs no plaintext.
        """
        if not isinstance(username, Username):
            return InvalidUserAccount("username")
        if not isinstance(password, Password):
            return InvalidUserAccount("password")
        validated = cls.validate_password(username=username, raw=password.value)
        if isinstance(validated, InvalidRegistrationValue):
            return validated
        return cls.from_persisted(
            user_id=user_id, status=UserAccessStatus.ACTIVE, version=0,
            credential_generation=0, admin_eligible=admin_eligible,
            username=username, email=email, password_hash=password_hash,
        )

    @classmethod
    def from_persisted(
        cls, *, user_id: str, status: UserAccessStatus, version: int,
        credential_generation: int, admin_eligible: bool, username: Username,
        email: Email, password_hash: str,
    ) -> "UserAccount | InvalidUserAccount":
        """Lifetime value guards; preserve recorded state, never reset defaults."""
        if not isinstance(user_id, str) or not user_id.strip():
            return InvalidUserAccount("user_id")
        if not isinstance(status, UserAccessStatus):
            return InvalidUserAccount("status")
        if type(version) is not int or version < 0:
            return InvalidUserAccount("version")
        if type(credential_generation) is not int or credential_generation < 0:
            return InvalidUserAccount("credential_generation")
        if type(admin_eligible) is not bool:
            return InvalidUserAccount("admin_eligible")
        if not isinstance(username, Username):
            return InvalidUserAccount("username")
        if not isinstance(email, Email):
            return InvalidUserAccount("email")
        if not isinstance(password_hash, str) or not password_hash:
            return InvalidUserAccount("password_hash")
        account = object.__new__(cls)
        for name, value in dict(
            user_id=user_id, username=username, email=email, password_hash=password_hash,
            status=status, version=version, credential_generation=credential_generation,
            admin_eligible=admin_eligible,
        ).items():
            object.__setattr__(account, name, value)
        return account

    @staticmethod
    def validate_password(
        *, username: Username, raw: str,
    ) -> Password | InvalidRegistrationValue[Literal["invalid_password"]]:
        """Shared account password-value/username rule, before any hashing."""
        password = Password.from_input(raw)
        if isinstance(password, InvalidRegistrationValue):
            return password
        if password.value.casefold() == username.value:
            return InvalidRegistrationValue("invalid_password")
        return password

    def login_eligibility(self, *, admin_required: bool) -> LoginEligibility:
        """Account-only login eligibility; the caller still verifies the password.

        admin_required is trusted operation configuration, never a client role.
        Malformed trusted configuration raises InvalidAccountDecisionFacts;
        login/admin_login Interactors propagate it unchanged to the deferred outer
        handler, without a normal outcome or retry. Loading adapters do not execute
        this decision. A lookup decision is not an issuance grant and does not
        authorize a later resource mutation.
        """
        if type(admin_required) is not bool:
            raise InvalidAccountDecisionFacts("Malformed trusted login requirement")
        if self.status is not UserAccessStatus.ACTIVE:
            return LoginEligibility.DENIED
        if admin_required and not self.admin_eligible:
            return LoginEligibility.DENIED
        return LoginEligibility.ALLOWED

    def credential_eligibility(self, *, generation: int | None) -> CredentialEligibility:
        """Current account/generation decision for issuance and access validation.

        Token authenticity, expiry and issuer/audience are external verified facts.
        Missing/malformed/stale claimed generations are ordinary denials, not
        exceptions. The caller must never replace them with the current generation.
        Adapters serialize this decision with account transitions; a stale read
        alone is insufficient. No credentials are issued by this Entity.
        """
        if (
            type(generation) is not int or generation < 0
            or self.status is not UserAccessStatus.ACTIVE
            or generation != self.credential_generation
        ):
            return CredentialEligibility.DENIED
        return CredentialEligibility.ALLOWED

    def permits_password_change(self) -> bool:
        """ACTIVE-only across ALL password-change channels."""
        return self.status is UserAccessStatus.ACTIVE

    def change_password(
        self, *, password: Password, password_hash: str, expected_version: int,
    ) -> "PasswordChangeDecision":
        """Advance revision/generation once; preserve identity/status/eligibility.

        The caller authenticates/authorizes the operation and supplies a hash of
        this candidate. This Entity never verifies/hashes secrets or issues tokens.
        Rejections leave the Entity unchanged. Persistence serializes the exact
        transition with all account writers and enforces the old-session barrier.
        The distinct-current-password rule belongs only to self-service for now.
        """
        if not isinstance(password, Password):
            return InvalidPasswordChange("password")
        if not isinstance(password_hash, str) or not password_hash:
            return InvalidPasswordChange("password_hash")
        if type(expected_version) is not int or expected_version < 0:
            return InvalidPasswordChange("expected_version")
        if not self.permits_password_change():
            return PasswordChangeRejection.INACTIVE
        if self.version != expected_version:
            return PasswordChangeRejection.VERSION_CONFLICT
        validated = self.validate_password(username=self.username, raw=password.value)
        if isinstance(validated, InvalidRegistrationValue):
            return validated
        return self._transition(
            status=self.status, password_hash=password_hash,
            credential_generation=self.credential_generation + 1,
        )

    def change_status(
        self, *, status: UserAccessStatus, expected_version: int,
    ) -> "AccountAccessChange":
        """Admin-target protection precedes revision and already-set decisions.

        Each change advances revision once. Suspension advances generation;
        restoration preserves it. Both retain identity/credentials/eligibility.
        Actor permission is a separate policy decision inside the atomic scope;
        this method alone is not an authorization grant. Rejections have no effects.
        """
        if not isinstance(status, UserAccessStatus):
            return InvalidAccountAccessChange("status")
        if type(expected_version) is not int or expected_version < 0:
            return InvalidAccountAccessChange("expected_version")
        if self.admin_eligible:
            return AccountAccessRejection.ADMIN_TARGET_FORBIDDEN
        if self.version != expected_version:
            return AccountAccessRejection.VERSION_CONFLICT
        if self.status is status:
            return AccountAccessRejection.ALREADY_SET
        generation = self.credential_generation
        if status is UserAccessStatus.SUSPENDED:
            generation += 1
        return self._transition(
            status=status, password_hash=self.password_hash,
            credential_generation=generation,
        )

    def _transition(
        self, *, status: UserAccessStatus, password_hash: str, credential_generation: int,
    ) -> "UserAccountTransition":
        """Internal construction after public operations have validated a change."""
        after = object.__new__(UserAccount)
        for name, value in dict(
            user_id=self.user_id, username=self.username, email=self.email,
            password_hash=password_hash, status=status, version=self.version + 1,
            credential_generation=credential_generation, admin_eligible=self.admin_eligible,
        ).items():
            object.__setattr__(after, name, value)
        transition = object.__new__(UserAccountTransition)
        object.__setattr__(transition, "before", self)
        object.__setattr__(transition, "after", after)
        return transition


@dataclass(frozen=True, init=False)
class UserAccountTransition:
    """Entity-approved before/after state, not another independently writable Entity."""

    before: UserAccount
    after: UserAccount

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("Use UserAccount.change_status or UserAccount.change_password")


AccountAccessChange = UserAccountTransition | AccountAccessRejection | InvalidAccountAccessChange
PasswordChangeDecision = (
    UserAccountTransition | PasswordChangeRejection
    | InvalidPasswordChange | InvalidRegistrationValue[Literal["invalid_password"]]
)
