from typing import Protocol

from .request import AccessRequirement, AuthorizeRequest


class AuthorizeInputBoundary(Protocol):
    def execute(
        self, request: AuthorizeRequest, *, requirement: AccessRequirement,
    ) -> None:
        """Validate access and emit one final outcome via the Output Boundary.

        requirement comes from trusted server-side configuration, never a client
        role or permission claim. No default requirement: callers must choose.
        Invalid trusted configuration raises InvalidAccessRequirement; never
        downgrade an unknown requirement to authenticated. Non-string or blank
        credentials are rejected locally without consulting the validator. Other
        credentials are passed unchanged, never stripped or normalized.
        AccessValidator returns only the verified subject/original generation;
        it never reads account eligibility or grants permission. Supply those
        facts and the unchanged token to AccessAccountStore.protect. Inside its
        protected scope the Interactor calls UserAccount.credential_eligibility,
        then invokes UserAccount.administrative_eligibility for ADMIN requests.
        This is the same ACTIVE-admin rule used by every administrative operation;
        the trusted requirement is never a client claim.
        Missing/malformed claimed generation is None and denied by the Entity;
        never substitute the current account generation. Missing account or
        invalid credential/account state emits unauthenticated. Eligible non-admins
        requesting admin access emit forbidden; other valid access succeeds.
        Scoped outcomes emit only after successful exit. Adapters protect all
        decision facts, never execute business decisions or suppress exceptions.
        Production freshness/barrier/concurrency guarantees remain deferred.
        Dependency/contract failures propagate to the deferred outer handler
        without presentation or retry. There is no second returned result.
        This decision is not an atomic authorization grant for a later mutation;
        operation-specific use cases must enforce their own authorization rules.
        """
        ...
