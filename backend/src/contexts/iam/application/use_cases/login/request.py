from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoginRequest:
    username: str
    password: str = field(repr=False)
