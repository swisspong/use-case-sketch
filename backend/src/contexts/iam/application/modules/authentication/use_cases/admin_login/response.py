from dataclasses import dataclass, field
from typing import Literal, Union


@dataclass(frozen=True)
class AdminLoginSuccess:
    token: str = field(repr=False)


@dataclass(frozen=True)
class AdminLoginFailure:
    code: Literal["invalid_credentials"]


AdminLoginResult = Union[AdminLoginSuccess, AdminLoginFailure]
