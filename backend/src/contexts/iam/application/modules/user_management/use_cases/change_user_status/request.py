from dataclasses import dataclass


@dataclass(frozen=True)
class ChangeUserStatusRequest:
    """Application input; trusted actor identity is deliberately separate.

    Raw application values are validated by the Interactor, never normalized:
    user_id must be a nonblank string; status is exactly active or suspended;
    expected_version is a nonnegative integer (not bool) from a prior snapshot.
    Validation order is user_id, status, version. Reject malformed values through
    the output port before invoking any dependency. No framework types here.
    """

    user_id: str
    status: str
    expected_version: int
