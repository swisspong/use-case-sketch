from typing import Protocol

from .request import ChangeUserStatusRequest


class ChangeUserStatusInputBoundary(Protocol):
    def execute(self, request: ChangeUserStatusRequest, *, actor_id: str) -> None:
        """Change user access state and emit one final outcome via the output port.

        actor_id must come from authenticated caller context, not request data.
        Invalid user_id/status/version emits invalid_user_id/invalid_status/
        invalid_version before dependency calls, with no normalization or coercion.
        Open StatusChangeUoW for the trusted actor and exact target. The Interactor
        calls IdentityStatusPolicy using protected authoritative facts; the policy
        delegates target invariants/transitions to the UserAccount Entity.
        Every Identity access-update channel honors those same Entity invariants.
        Adapters obtain facts/persist/enforce atomicity, never execute the policy or
        map domain rejections. Commit only an approved transition, once; rejections
        have no commit or credential effects. Scope exit never auto-commits or
        suppresses failures. Emit the final outcome only after successful exit.
        expected_version prevents stale changes; emit status_conflict without retry
        when the target revision differs. Success includes the committed new version.
        Suspension invalidates old credentials permanently; restoration needs fresh
        login. Previously authorized requests may finish; subsequent checks deny
        suspended users. Enforcement consumers and their integration remain deferred.
        System failures propagate without a normal outcome; no automatic retries.
        The caller/transport adapter and authentication middleware are deferred.
        """
        ...
