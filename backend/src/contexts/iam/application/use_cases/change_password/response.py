from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ChangePasswordSuccess:
    """Password committed; all prior sessions, including this one, are invalid."""


@dataclass(frozen=True)
class ChangePasswordFailure:
    code: Literal[
        "unauthenticated", "invalid_current_password", "invalid_new_password",
        "password_unchanged", "password_conflict",
    ]


ChangePasswordResult = ChangePasswordSuccess | ChangePasswordFailure
