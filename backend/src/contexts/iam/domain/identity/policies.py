"""Identity actor authorization; account lifecycle belongs to UserAccount."""

from enum import Enum

from .user_account import (
    AdministrativeEligibility, UserAccount, AccountAccessRejection,
    UserAccountTransition, InvalidAccountAccessChange,
)
from .user_access_status import UserAccessStatus


class IdentityStatusRejection(str, Enum):
    ADMIN_REQUIRED = "admin_required"
    USER_NOT_FOUND = "user_not_found"
    ADMIN_TARGET_FORBIDDEN = "admin_target_forbidden"
    VERSION_CONFLICT = "version_conflict"
    ALREADY_SET = "already_set"


IdentityStatusDecision = UserAccountTransition | IdentityStatusRejection


class InvalidIdentityStatusFacts(RuntimeError):
    """Malformed trusted policy arguments, not an expected business rejection."""


class IdentityStatusPolicy:
    @staticmethod
    def decide(
        *, actor: UserAccount | None, target: UserAccount | None,
        status: UserAccessStatus, expected_version: int,
    ) -> IdentityStatusDecision:
        """Authorize the actor before asking the Entity for a transition.

        The administrative operation requires UserAccount's shared ACTIVE-admin
        approval from the current actor before disclosing any target decision.
        Missing/suspended/non-admin actors receive ADMIN_REQUIRED. UserAccount owns
        this rule across all administrative operations and the target invariants.
        This policy performs no I/O. Facts, decision, persistence and access-barrier
        enforcement must share one protected atomic scope; do not use a permissive
        pre-check followed by unconditional writing. The orchestrating caller invokes
        this policy; persistence adapters do not choose or execute its rules.
        Malformed trusted arguments or undeclared Entity decisions raise
        InvalidIdentityStatusFacts, translated by the orchestrating caller to its
        system exception. They never become an authorization grant or rejection.
        """
        if (
            (actor is not None and not isinstance(actor, UserAccount))
            or not isinstance(status, UserAccessStatus)
            or type(expected_version) is not int
            or expected_version < 0
        ):
            raise InvalidIdentityStatusFacts("Malformed trusted status-change arguments")
        if actor is None:
            return IdentityStatusRejection.ADMIN_REQUIRED
        eligibility = actor.administrative_eligibility()
        if eligibility is AdministrativeEligibility.DENIED:
            return IdentityStatusRejection.ADMIN_REQUIRED
        if eligibility is not AdministrativeEligibility.ALLOWED:
            raise InvalidIdentityStatusFacts("Entity returned an undeclared administrative decision")
        if target is None:
            return IdentityStatusRejection.USER_NOT_FOUND
        if not isinstance(target, UserAccount):
            raise InvalidIdentityStatusFacts("Malformed authoritative target Entity")
        decision = target.change_status(status=status, expected_version=expected_version)
        if isinstance(decision, UserAccountTransition):
            return decision
        if decision is AccountAccessRejection.ADMIN_TARGET_FORBIDDEN:
            return IdentityStatusRejection.ADMIN_TARGET_FORBIDDEN
        if decision is AccountAccessRejection.VERSION_CONFLICT:
            return IdentityStatusRejection.VERSION_CONFLICT
        if decision is AccountAccessRejection.ALREADY_SET:
            return IdentityStatusRejection.ALREADY_SET
        if isinstance(decision, InvalidAccountAccessChange):
            raise InvalidIdentityStatusFacts("Malformed trusted Entity transition input")
        raise InvalidIdentityStatusFacts("Entity returned an undeclared status decision")
