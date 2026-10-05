"""Inward-owned authorization capabilities inside IAM.

Identity owns account state/generation/admin eligibility; AuthorizeInteractor
executes its decisions. Adapters verify credentials, obtain/protect facts and
translate technical failures, never execute account eligibility rules.
Production protection/barriers and resource-specific authorization are deferred.
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, Union

from contexts.iam.domain.identity.user_account import UserAccount


@dataclass(frozen=True)
class ValidatedAccess:
    """Legacy projection retained for imports, NOT a current port result/grant.

    Current consumers use VerifiedCredential and the real protected UserAccount.
    Returning this from AccessValidator is a contract breach.
    """

    actor_id: str
    admin_eligible: bool


@dataclass(frozen=True)
class VerifiedCredential:
    """Technical verification facts, not an account eligibility/permission grant.

    actor_id is the nonblank verified subject, never a client-supplied identity.
    credential_generation is the authenticated claim/opaque binding; missing or
    malformed claims are represented by None, NEVER the current account generation.
    Integer values, including stale/negative generations, remain domain inputs.
    No token role claim or account defaults belong in this projection.
    """

    actor_id: str
    credential_generation: int | None


@dataclass(frozen=True)
class UnauthenticatedAccess:
    """Technology-level credential rejection; no identity/details disclosed."""


AccessValidationResult = Union[VerifiedCredential, UnauthenticatedAccess]


class AccessValidationError(RuntimeError):
    """Known verification/scope/read/exit/corruption failure; no normal outcome."""


class AccessValidator(Protocol):
    def validate(self, token: str) -> AccessValidationResult:
        """Verify the exact credential's authenticity, expiry and issuer/audience.

        Invalid/expired/revoked technology credentials -> adapter ->
        UnauthenticatedAccess -> Interactor -> unauthenticated -> deferred Presenter.
        Success returns only the verified subject and original authenticated
        generation. Decode absent/malformed generation claims as None, not a grant.
        Do not load/filter accounts or execute ACTIVE/generation/admin decisions.
        A verified credential is NOT authorization or a later mutation grant.

        Recognized verification/key/provider outage -> adapter ->
        AccessValidationError -> outer handler without outcome/retry. An outage is
        not invalid input. Unexpected errors propagate. Undeclared/malformed
        trusted results -> Interactor -> InvalidAccessValidationResult -> handler.
        Never log tokens or expose provider/exception text. Production cryptography
        and verification tests deferred; mocks verify arguments, not authenticity.
        """
        ...


class AccessAccountStore(Protocol):
    def protect(
        self, *, credential: VerifiedCredential, token: str,
    ) -> AbstractContextManager[UserAccount | None]:
        """Protect credential usability and current account facts for one decision.

        token is the unchanged credential already verified by AccessValidator;
        credential carries that SAME verified subject/original generation. Both
        are supplied so technical freshness/revocation can be coordinated with
        the account decision rather than trusting an indefinitely valid pre-check.
        Recheck technical validity as needed at the protected decision point:
        expired/revoked/invalid credential or missing subject -> None. Never
        substitute another subject/generation or upgrade the verification snapshot.
        No token issuance, refresh, account mutation or business decision here.

        Yield the full authoritative UserAccount bound to credential.actor_id,
        including suspended/non-admin accounts and stale-generation accounts.
        Rehydrate with from_persisted, preserving state, not creation defaults.
        The Interactor invokes credential_eligibility with the ORIGINAL credential
        generation, branches, then checks current admin_eligible when required.
        Adapters must NOT call domain eligibility or filter these business facts.

        Protect all mutable facts used by the decision, including credential
        usability and account state/generation/admin eligibility, through evaluation
        and exit. Serialize with all relevant credential/account/role writers and
        the same suspension/password barriers used by login and issuance. Decisions
        after committed suspension/role revocation must observe it; restoration
        never upgrades old credentials. Previously authorized requests may finish;
        this scope is not authorization for a later atomic resource mutation.
        A local DB transaction alone cannot protect remote provider facts; actual
        freshness, coordination and barrier enforcement require adapter tests.

        Scope operations only read/protect facts: no business writes/provider
        effects/implicit commit. Roll back uncommitted technical work and release
        resources on every exit. NEVER suppress exceptions. Emit any scoped
        outcome only after successful exit; do not retry entry/read/exit failures.
        InvalidUserAccount while loading or known scope/read/storage/corruption/
        provider/exit failure -> adapter -> AccessValidationError -> outer handler,
        no outcome/retry. Leaked rejection, undeclared facts or wrong identity ->
        Interactor -> InvalidAccessValidationResult -> handler. Unexpected errors
        propagate. Exit/presentation are not atomically reversible; presentation
        failure must not cause revalidation. Concrete adapters remain deferred.
        """
        ...
