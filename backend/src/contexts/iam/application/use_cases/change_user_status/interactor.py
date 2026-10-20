"""Account access-state orchestration within IAM; production integration deferred.

Caller / Controller [deferred] supplies trusted actor_id
  -> ChangeUserStatusInputBoundary -> ChangeUserStatusInteractor
     -> UserAccessStatus.parse
     -> StatusChangeUoW.begin -> atomic production adapter [deferred]
     -> inside the protected scope, the Interactor calls:
        -> StatusChangeTransaction.facts [adapter deferred] -> authoritative facts
        -> IdentityStatusPolicy.decide -> UserAccount.change_status
        -> approved transition -> StatusChangeTransaction.commit [adapter deferred]
     -> scope exit (no implicit commit; never suppress exceptions)
     -> ChangeUserStatusOutputBoundary.present
        -> Presenter -> ViewModel / transport output [deferred]
The Interactor calls the real domain policy inside the protected actor/target
scope and maps domain decisions directly. The actor Entity must satisfy the shared
ACTIVE-admin rule before any target decision. Identity owns shared target invariants,
revision and credential generation; adapters only obtain facts/persist/enforce.
Known dependency failures -> adapters -> UserStatusManagementError -> outer handler
[deferred]. InvalidIdentityStatusFacts -> Interactor -> UserStatusManagementError;
malformed dependency data -> InvalidUserStatusChangeResult -> outer handler.
Unexpected failures propagate; no outcome/retry on failure. Presentation occurs
only after successful scope exit and cannot roll back an explicit commit.
"""

from .ports import (
    InvalidUserStatusChangeResult, StatusChangeFacts, StatusChangeUoW, UserStatusManagementError,
)
from contexts.iam.domain.identity.policies import (
    IdentityStatusPolicy, IdentityStatusRejection, InvalidIdentityStatusFacts,
)
from contexts.iam.domain.identity.user_account import UserAccount, UserAccountTransition
from contexts.iam.domain.identity.user_access_status import InvalidUserAccessStatus, UserAccessStatus

from .input_boundary import ChangeUserStatusInputBoundary
from .output_boundary import ChangeUserStatusOutputBoundary
from .request import ChangeUserStatusRequest
from .response import ChangeUserStatusFailure, ChangeUserStatusResult, ChangeUserStatusSuccess


class ChangeUserStatusInteractor(ChangeUserStatusInputBoundary):
    def __init__(
        self,
        uow: StatusChangeUoW,
        output: ChangeUserStatusOutputBoundary,
    ) -> None:
        self._uow = uow
        self._output = output

    def execute(self, request: ChangeUserStatusRequest, *, actor_id: str) -> None:
        if not isinstance(request.user_id, str) or not request.user_id.strip():
            self._output.present(ChangeUserStatusFailure("invalid_user_id"))
            return
        status = UserAccessStatus.parse(request.status)
        if isinstance(status, InvalidUserAccessStatus):
            self._output.present(ChangeUserStatusFailure("invalid_status"))
            return
        if type(request.expected_version) is not int or request.expected_version < 0:
            self._output.present(ChangeUserStatusFailure("invalid_version"))
            return
        outcome: ChangeUserStatusResult
        with self._uow.begin(actor_id=actor_id, user_id=request.user_id) as tx:
            facts = tx.facts()
            if (
                not isinstance(facts, StatusChangeFacts)
                or facts.actor_id != actor_id
                or (
                    facts.actor is not None
                    and (
                        not isinstance(facts.actor, UserAccount)
                        or facts.actor.user_id != actor_id
                    )
                )
                or (
                    facts.target is not None
                    and (
                        not isinstance(facts.target, UserAccount)
                        or facts.target.user_id != request.user_id
                    )
                )
            ):
                raise InvalidUserStatusChangeResult("Transaction returned malformed or mismatched facts")
            try:
                decision = IdentityStatusPolicy.decide(
                    actor=facts.actor, target=facts.target,
                    status=status, expected_version=request.expected_version,
                )
            except InvalidIdentityStatusFacts as exc:
                raise UserStatusManagementError("Invalid authoritative status-change facts") from exc
            if isinstance(decision, UserAccountTransition):
                if tx.commit(transition=decision) is not None:
                    raise InvalidUserStatusChangeResult(
                        "Transaction returned an undeclared commit acknowledgement",
                    )
                outcome = ChangeUserStatusSuccess(
                    decision.after.user_id, decision.after.status, decision.after.version,
                )
            elif decision is IdentityStatusRejection.ADMIN_REQUIRED:
                outcome = ChangeUserStatusFailure("forbidden")
            elif decision is IdentityStatusRejection.USER_NOT_FOUND:
                outcome = ChangeUserStatusFailure("user_not_found")
            elif decision is IdentityStatusRejection.ADMIN_TARGET_FORBIDDEN:
                outcome = ChangeUserStatusFailure("admin_target_forbidden")
            elif decision is IdentityStatusRejection.VERSION_CONFLICT:
                outcome = ChangeUserStatusFailure("status_conflict")
            elif decision is IdentityStatusRejection.ALREADY_SET:
                outcome = ChangeUserStatusFailure("status_already_set")
            else:
                raise InvalidUserStatusChangeResult("Policy returned an undeclared status decision")
        self._output.present(outcome)
