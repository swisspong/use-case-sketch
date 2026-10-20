"""Atomic access-state scope owned by IAM's change_user_status use case.

The Interactor orchestrates facts -> IdentityStatusPolicy -> UserAccount transition
-> explicit commit -> post-scope outcome. Identity remains the sole account-state,
credential-generation and eligibility owner. These inward-owned ports are not
another context's public API; production adapters only obtain facts/persist/enforce.
Password rotation owns PasswordAccountStore in use_cases.change_password.ports,
with the same Entity
and concurrency/barrier obligations. Production integration remains deferred.
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from contexts.iam.domain.identity.user_account import UserAccount, UserAccountTransition


class InvalidUserStatusChangeResult(RuntimeError):
    """Malformed/mismatched facts, invalid transition/acknowledgement or inner decision."""


class UserStatusManagementError(RuntimeError):
    """Scope/read/commit/barrier/cleanup or corrupt-facts failure; commit may be uncertain."""


@dataclass(frozen=True)
class StatusChangeFacts:
    """Authoritative actor/target Entities, not another independently writable model.

    actor_id binds the scope to the trusted caller; actor is that exact UserAccount
    or None if missing. Return suspended/non-admin actors too: the Entity and policy
    own the shared ACTIVE-admin rule, not an adapter-derived eligibility boolean.
    target is the exact requested UserAccount or None. Rehydrate both Entities with
    from_persisted, never creation defaults. Use these facts only inside their
    producing scope, before explicit commit; never reuse a committed/closed scope
    or upgrade a stale snapshot. A matching actor/target identity uses consistent
    authoritative state, not divergent snapshots.
    """

    actor_id: str
    actor: UserAccount | None
    target: UserAccount | None


class StatusChangeTransaction(Protocol):
    def facts(self) -> StatusChangeFacts:
        """Read one consistent authoritative actor/target snapshot for this scope.

        No mutation, credential change or provider effect. Return full actor and
        target Entities, including ineligible actors; never compute permissions.
        Preserve recorded username/email/hash/status/revision/generation/admin
        eligibility for both accounts; do not normalize corrupt persisted data.
        Bind both identities to begin's exact
        arguments. InvalidUserAccount or recognized read/corruption failures ->
        adapter -> UserStatusManagementError -> outer handler without commit,
        outcome or retry. Malformed/mismatched facts -> Interactor ->
        InvalidUserStatusChangeResult; malformed policy arguments -> Interactor
        translates InvalidIdentityStatusFacts to UserStatusManagementError.
        """
        ...

    def commit(self, *, transition: UserAccountTransition) -> None:
        """Commit one exact Entity-approved transition and the access barrier.

        Accept only UserAccount.change_status's transition from this scope's
        target snapshot, with unchanged identity/username/email/hash/eligibility.
        Persist its exact after state, including revision and credential generation;
        never recompute transitions, select defaults or overwrite a concurrent
        credential change. Reject invalid plans as InvalidUserStatusChangeResult
        before writing. At most one commit per scope; no further facts/mutations
        after commit, no implicit commit or retry. None is the ONLY successful
        acknowledgement, after durable commit AND barrier enforcement, not merely
        after staging a write. Recognized storage/concurrency/provider/barrier
        failures -> adapter -> UserStatusManagementError -> outer handler without
        outcome/retry; commit certainty may be unknown. Unexpected failures
        propagate. A non-None acknowledgement -> Interactor ->
        InvalidUserStatusChangeResult -> outer handler, never normal success.

        Suspension must deny ALL prior access/session/refresh credentials and old
        in-flight login grants, using Identity's advanced authoritative generation.
        Login lookup snapshots, issuance and access validation must honor that same
        state/generation. Restoration never revives old credentials or upgrades old
        snapshots; fresh login is required and this operation issues no credentials.
        After suspension commits, subsequent authorization decisions deny access;
        already-authorized requests may finish. An unexpired signed token alone or
        delayed cache invalidation is insufficient. A local DB transaction cannot
        make remote provider revocation atomic; adapters must implement a real
        barrier across those effects before acknowledging success.
        """
        ...


class StatusChangeUoW(Protocol):
    def begin(
        self, *, actor_id: str, user_id: str,
    ) -> AbstractContextManager[StatusChangeTransaction]:
        """Open an atomic actor/target scope; do not execute business policy here.

        actor_id is authenticated caller context, never a client-supplied role.
        IdentityStatusPolicy and UserAccount decisions run in the Interactor while
        this scope protects authoritative actor/target eligibility and account state
        through evaluation and commit (or no-commit exit). This includes the actor's
        ACTIVE status and admin eligibility, even when generation is unchanged.
        Concurrent role revocation, target-role changes, password rotation and
        status updates must
        serialize with this operation. Coordinate consistent lock ordering or
        equivalent protection across ALL account writers. A separate permissive
        pre-check or stale unconditional write is insufficient. Role changes must
        invalidate stale revisions or be checked under the same protection.
        Competing changes from one revision have at most one success; later
        decisions observe a version conflict. Production adapters obtain facts/
        persist/enforce, never choose business rules or map domain rejections;
        expected actor/target/version/status decisions stay in the Interactor.

        Creation/entry/read/commit/exit recognized failures -> adapter ->
        UserStatusManagementError -> outer handler without normal outcome/retry.
        Unexpected failures propagate. Without explicit commit there are ZERO
        business writes/credential/provider effects, on either normal or exceptional
        exit. Roll back uncommitted work and release resources on every exit.
        __exit__ never suppresses exceptions and never auto-commits. A successful
        explicit commit is already durable; exit/presentation failure cannot undo it
        and must not trigger another write. Present only after successful scope exit.
        Production adapters, barrier consumers and atomicity/race/integration tests
        remain deferred; unit mocks cannot prove these guarantees.
        """
        ...
