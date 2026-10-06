from dataclasses import dataclass, field
from typing import Literal, Union


@dataclass(frozen=True)
class LoginSuccess:
    token: str = field(repr=False)


@dataclass(frozen=True)
class LoginFailure:
    code: Literal["invalid_credentials"]


LoginResult = Union[LoginSuccess, LoginFailure]
