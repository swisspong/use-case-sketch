from typing import Protocol

from .request import ChangePasswordRequest


class ChangePasswordInputBoundary(Protocol):
    def execute(self, request: ChangePasswordRequest, *, actor_id: str) -> None:
        """Change only the authenticated caller's own password.

        actor_id comes from trusted authentication context, never form data.
        Both ordinary users and admins may change only their own passwords;
        no caller-supplied role or target user ID grants access to another account.
        UserAccount owns ACTIVE-only password changes across all channels, with
        version/generation advanced once and identity/status/eligibility preserved.
        Current password must match; new password follows the same value and
        username rules as registration and must differ from the current password.
        The distinct-current-password rule applies only to this use case for now.
        Commit the new hash and invalidation of ALL existing sessions atomically;
        success requires a fresh login, never returns a replacement token.
        Emit one terminal outcome through the Output Boundary on normal execution.
        System failures propagate to the deferred outer handler without an outcome
        or automatic retry. Presentation cannot roll back a committed change.
        """
        ...
