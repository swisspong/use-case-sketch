"""Registration capabilities within the Identity & Access Management context.

Identity's UserAccount Entity owns identity/credential/lifecycle invariants and
shared password rules. Registration orchestrates sign-up and selects non-admin
eligibility; it does not independently own account password rules. These ports
are inward-owned capabilities, not a separate context's public API. Production
adapters, Presenter and registration-to-login integration remain deferred.
Hashing capabilities/errors belong to application.password_ports.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from contexts.iam.domain.identity.user_account import UserAccount


@dataclass(frozen=True)
class RegisteredUser:
    user_id: str
    username: str
    email: str
    created_at: datetime


@dataclass(frozen=True)
class IdentityConflict:
    """Expected username/email rejection, never a generated-ID collision.

    If both fields conflict, report username first. The persistence adapter
    translates unique conflicts; an undeclared field breaches the store contract
    and the Interactor raises InvalidIdentityConflictResult.
    """

    field: Literal["username", "email"]


class UserIdGenerationError(RuntimeError):
    """The identity generator could not produce a candidate ID (system failure)."""


class InvalidGeneratedUserIdResult(RuntimeError):
    """Generator breached its nonblank-string result contract; no write is made."""


class UserRegistrationError(RuntimeError):
    """Storage/commit failed (certainty may be unknown), or ID retries exhausted."""


class GeneratedUserIdCollision(UserRegistrationError):
    """The candidate ID already exists; this attempt has NO effects.

    The adapter may raise this only for a recognized user-ID uniqueness collision
    after ensuring no partial writes or external effects. Timeouts, outages and
    uncertain commits must never be translated to this recoverable exception.
    """


class InvalidIdentityConflictResult(RuntimeError):
    """The store returned an identity conflict outside its declared fields."""


class InvalidRegisteredUserResult(RuntimeError):
    """Store success has mismatched canonical identity or invalid creation time."""


class UserIdGenerator(Protocol):
    def generate(self) -> str:
        """Return a nonblank candidate ID, preserved without normalization.

        This is not a uniqueness guarantee: the persistence boundary enforces ID
        uniqueness atomically. No account, credential or session is created here.
        Recognized generator/backend failures -> generator adapter ->
        UserIdGenerationError -> Interactor -> outer handler [deferred], without
        another write, presentation or automatic retry. Unexpected errors propagate.
        Malformed result -> UserAccount.create typed rejection -> Interactor ->
        InvalidGeneratedUserIdResult -> outer handler, before any write using it.
        The application, not the adapter, selects collision retry behavior.
        """
        ...


class UserRegistrationStore(Protocol):
    def create(self, *, account: UserAccount) -> RegisteredUser | IdentityConflict:
        """Atomically persist the supplied complete new account Entity.

        username/email/hash come only from account.username.value,
        account.email.value and account.password_hash: there is no competing
        independently writable representation of these values.

        Success means account.user_id, username/email/hash, status, version,
        credential generation and admin eligibility have committed together.
        UserAccount.create chooses ACTIVE/version 0/generation 0 across creation
        channels; registration chooses non-admin eligibility. Persist those exact
        values, never independently allocate/replace an ID or choose defaults.
        Rehydrate existing accounts through UserAccount.from_persisted; creation
        defaults must not reset recorded state. State, generation, eligibility and
        credentials are initialized atomically. After commit the account is eligible
        for immediate separate login, subject to later authoritative state changes;
        no approval/activation, token or session is issued here.
        Returned user_id equals account.user_id and returned username/email equal
        its canonical values; created_at is timezone-aware. Wrong success identity ->
        Interactor -> InvalidRegisteredUserResult -> outer handler, never retry.

        Enforce user ID, normalized username and normalized email uniqueness even
        under concurrency. Username/email conflicts -> adapter -> IdentityConflict
        (username first if both fields conflict) -> semantic rejection -> Presenter.
        Every conflict has no partial account/effects; a pre-check is insufficient.

        Recognized generated-ID uniqueness collision with confirmed zero effects
        -> adapter -> GeneratedUserIdCollision -> Interactor requests a new ID,
        creates a fresh Entity and tries again, at most 3 attempts including the
        first. Reuse the already computed password hash; request another candidate
        and create another Entity rather than resubmitting the prior one. Do not
        rehash. Exhaustion -> Interactor -> UserRegistrationError -> outer
        handler without a normal outcome. This guarantee is essential to safe
        recovery; uncertain rollback/effects must use UserRegistrationError instead.

        Other recognized storage/commit failures -> adapter -> UserRegistrationError
        -> Interactor propagates -> outer handler [deferred], without presentation
        or automatic retry. Unexpected errors propagate. Commit certainty may be
        unknown. Presentation failure cannot roll back a committed account and
        must not trigger another creation. Never expose secrets or raw failure text.
        Production uniqueness, zero-effects collision, atomic initialization and
        immediate-login guarantees need later adapter/integration tests; consumer
        mocks only verify application/domain behavior and bounded recovery.
        """
        ...
