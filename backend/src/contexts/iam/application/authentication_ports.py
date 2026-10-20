"""Authentication ports inside IAM; UserAccount is the sole account write model.

Lookup and protected scopes obtain authoritative facts; Interactors execute
login/credential eligibility. TokenIssuer performs only technical issuance.
Concrete adapters, concurrency/barrier enforcement and integration tests deferred.
Lookup ports belong beside login/admin_login; their shared lookup failures live
here. Password-processing capabilities belong to application.password_ports.
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

from contexts.iam.domain.identity.user_account import UserAccount


@dataclass(frozen=True)
class LoginAccount:
    """Legacy projection retained for imports; no current lookup port returns it.

    Current consumers require UserAccount to execute local business decisions.
    This projection is not a competing write model or an eligibility grant.
    """

    user_id: str
    password_hash: str = field(repr=False)
    credential_generation: int


class AccountLookupError(RuntimeError):
    """Known account lookup/storage/corruption failure; no normal outcome."""


class InvalidLoginAccountResult(RuntimeError):
    """Leaked factory rejection, mismatched username or undeclared domain decision."""


class LoginGrantError(RuntimeError):
    """Known protected-scope creation/entry/read/exit or corruption failure."""


class InvalidLoginGrantResult(RuntimeError):
    """Scope returned undeclared facts, wrong identity or invalid inner decision."""


class LoginGrantStore(Protocol):
    def protect(self, *, user_id: str) -> AbstractContextManager[UserAccount | None]:
        """Protect current account facts through local decision and token issuance.

        user_id is the exact password-verified lookup identity, never client claims.
        Entry yields the full current authoritative UserAccount for that identity,
        or None if missing. Rehydrate recorded state, never creation defaults.
        The Interactor invokes credential_eligibility using the ORIGINAL lookup
        generation. For admin_login it also invokes administrative_eligibility on
        this current Entity. TokenIssuer is called only if all decisions allow it.
        Never execute eligibility here, replace the supplied generation, upgrade
        an old login snapshot or select business defaults in an adapter.

        Protect every mutable fact used by that decision through issuance and exit;
        serialize with ALL account/status/credential writers and their suspension
        barriers, using consistent lock ordering or equivalent protection. A stale
        read or permissive pre-check followed by unconditional signing is not enough.
        For admin_login, protect current ACTIVE status AND admin eligibility
        through issuance and exit, serializing with role revocation even if it
        leaves credential generation unchanged. Ordinary login does not require
        admin eligibility. Neither this scope nor a DB transaction alone makes
        remote signing/provider effects atomic.

        Scope-owned operations only read/protect facts: no account/credential/provider
        writes, no explicit or implicit commit. Exit releases protection on every
        path, rolls back any uncommitted technical work and NEVER suppresses errors.
        Rejection has zero issuance effects. Present rejection/success only after
        successful exit. Completed issuer effects cannot be rolled back by exit or
        presentation failure; those failures produce no outcome/retry and leave
        issuance certainty possibly unknown. Scope release precedes success delivery.
        A later suspension can invalidate even a token already issued/returned.

        Missing/credential denial -> Interactor -> invalid_credentials -> Presenter.
        InvalidUserAccount while loading or known creation/entry/read/exit/storage
        failure -> scope adapter -> LoginGrantError -> outer handler, no outcome or
        retry. Leaked factory rejection/undeclared facts/wrong user_id -> Interactor
        -> InvalidLoginGrantResult -> outer handler before issuance/presentation.
        Unexpected errors propagate. Never log secrets or expose provider messages.
        Production protection/barrier/race guarantees require integration tests;
        application mocks only verify decisions, arguments and outcome timing.
        """
        ...


class TokenIssuanceError(RuntimeError):
    """Known signing/provider issuance failure; certainty may be unknown."""


class InvalidTokenIssuanceResult(RuntimeError):
    """Issuer returned an undeclared result or invalid token data.

    Login/admin_login Interactors detect this breach and propagate it to the
    deferred outer handler without a normal outcome or retry.
    """


@dataclass(frozen=True)
class IssuedToken:
    """Nonempty unforgeable access token for the supplied identity/generation."""

    token: str = field(repr=False)


@dataclass(frozen=True)
class LoginGrantRejected:
    """Legacy result retained for imports; no current issuer returns this variant.

    The Interactor now handles credential eligibility before technical issuance.
    Returning this from TokenIssuer is a contract breach, not a business rejection.
    """


TokenIssueResult = IssuedToken | LoginGrantRejected  # Legacy union, not a current port contract.


class TokenIssuer(Protocol):
    def issue(
        self, *, user_id: str, credential_generation: int, ttl: timedelta,
    ) -> IssuedToken:
        """Issue only after the Interactor's protected domain approval.

        No account lookup, login/credential eligibility decision, snapshot upgrade
        or business rejection here. The caller invokes this inside LoginGrantStore's
        protected scope with the exact verified identity/ORIGINAL generation.
        Bind authenticated token data (or an opaque-token equivalent) to those exact
        values. AccessValidator verifies that credential binding; AuthorizeInteractor
        evaluates Identity's current state/generation inside AccessAccountStore's
        protected scope, including suspension/restoration and password barriers.
        No assertion that a token remains usable until expiry is implied.

        ttl is a positive application-selected duration, never client input or an
        adapter default. login/admin_login select 15 minutes; other channels' rules
        are not established. Translate ttl to expiry, never extend/replace it, and
        enforce validity for no more than ttl from issuance. Earlier invalidation
        still applies. JWT versus opaque credentials is not prescribed.
        A local transaction cannot roll back remote issuance; adapters coordinate
        technical issuance with the protected scope/barrier contract, not a flag.

        Recognized signing/provider failure -> issuer adapter -> TokenIssuanceError
        -> Interactor propagates -> outer handler, without outcome/retry. Unexpected
        errors propagate. Issuance certainty may be unknown. Undeclared results or
        empty/non-string token -> Interactor -> InvalidTokenIssuanceResult ->
        outer handler, never false success. Never log
        secrets or expose provider/exception text. Issuance, exit and presentation
        are not atomically reversible. Actual cryptography, expiry, barriers and
        provider coordination require later adapter/integration tests.
        """
        ...
