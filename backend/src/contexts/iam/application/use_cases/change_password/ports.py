"""IAM self-service password persistence; UserAccount is the sole write model.

The former PasswordAccount wrapper is replaced by the complete UserAccount.
Production persistence and session/barrier enforcement remain deferred.
"""

from dataclasses import dataclass
from typing import Protocol

from contexts.iam.domain.identity.user_account import UserAccountTransition, UserAccount


@dataclass(frozen=True)
class PasswordAccountUnavailable:
    """No account exists for the authenticated caller; no data disclosed."""


@dataclass(frozen=True)
class PasswordChanged:
    """The supplied password transition and old-credential barrier committed."""


@dataclass(frozen=True)
class PasswordChangeConflict:
    """The authoritative account no longer matches the snapshot; zero effects."""


PasswordCommitResult = PasswordChanged | PasswordAccountUnavailable | PasswordChangeConflict


class PasswordStoreError(RuntimeError):
    """Known lookup/storage/corruption/barrier failure; commit may be uncertain."""


class InvalidPasswordStoreResult(RuntimeError):
    """The store breached its declared Entity/result or identity-binding contract."""


class PasswordAccountStore(Protocol):
    def load(self, *, actor_id: str) -> UserAccount | PasswordAccountUnavailable:
        """Read the complete authoritative Entity from one consistent snapshot.

        Bind identity to the exact trusted actor_id, never another target account.
        Rehydrate with UserAccount.from_persisted and recorded Username/Email values;
        do not apply creation defaults or normalize corrupt stored values into use.
        Return suspended accounts too: the inner layer decides eligibility.
        Missing -> adapter -> PasswordAccountUnavailable -> Interactor ->
        unauthenticated -> deferred Presenter. InvalidUserAccount during loading
        or known storage/corruption failure -> adapter -> PasswordStoreError ->
        outer handler, without hashing/write/presentation/retry. Undeclared result
        or wrong identity -> Interactor -> InvalidPasswordStoreResult -> outer
        handler. Unexpected errors propagate. Never log or present the hash.
        """
        ...

    def commit(self, *, transition: UserAccountTransition) -> PasswordCommitResult:
        """Compare-and-set the Entity-approved password transition atomically.

        Only submit UserAccount.change_password's successful transition. That
        Entity owns ACTIVE-only eligibility, password rules and version/generation
        increments across ALL password-change channels. Persist the exact after
        Entity, including its new hash; do not accept an independent hash/state or
        invent transitions/defaults in the adapter.
        Serialize with ALL account/credential/status writers and compare the whole
        before snapshot, including identity, username/email, admin eligibility,
        status, revision, generation and hash. Missing -> PasswordAccountUnavailable;
        mismatch -> PasswordChangeConflict. Both have zero effects. No unconditional
        write after a pre-check, snapshot upgrade or automatic retry.
        Commit the new hash/state and enforce that ALL prior access/session/refresh
        credentials and in-flight login snapshots cannot grant future access, even
        after restoration. No replacement token is issued. Authentication issuance
        and authorization must honor the same authoritative generation.
        A local transaction cannot make remote provider effects atomic. Production
        barrier, race and atomicity guarantees require adapter/integration tests.
        Expected commit decision -> adapter -> declared result -> Interactor ->
        semantic outcome -> deferred Presenter. Known storage/commit/provider/barrier
        failure -> adapter -> PasswordStoreError -> outer handler without outcome
        or retry; commit certainty may be unknown. Unexpected failures propagate.
        Undeclared result -> Interactor -> InvalidPasswordStoreResult -> handler.
        Presentation failure cannot roll back a commit or trigger another write.
        Never expose secrets or technology failure messages.
        """
        ...
