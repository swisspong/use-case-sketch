from dataclasses import dataclass, field


@dataclass(frozen=True)
class AdminLoginRequest:
    username: str
    password: str = field(repr=False)
