from dataclasses import dataclass
from typing import Literal, Union

from contexts.iam.domain.identity.user_access_status import UserAccessStatus


@dataclass(frozen=True)
class ChangeUserStatusSuccess:
    user_id: str
    status: UserAccessStatus
    version: int


@dataclass(frozen=True)
class ChangeUserStatusFailure:
    code: Literal[
        "forbidden", "user_not_found", "status_already_set", "admin_target_forbidden",
        "status_conflict", "invalid_user_id", "invalid_status", "invalid_version",
    ]


ChangeUserStatusResult = Union[ChangeUserStatusSuccess, ChangeUserStatusFailure]
