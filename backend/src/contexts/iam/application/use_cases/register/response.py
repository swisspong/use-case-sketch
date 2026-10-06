from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Union


@dataclass(frozen=True)
class RegistrationSuccess:
    user_id: str
    username: str
    email: str
    created_at: datetime


@dataclass(frozen=True)
class RegistrationFailure:
    code: Literal[
        "invalid_username", "invalid_email", "invalid_password",
        "username_taken", "email_taken",
    ]


RegisterResult = Union[RegistrationSuccess, RegistrationFailure]
