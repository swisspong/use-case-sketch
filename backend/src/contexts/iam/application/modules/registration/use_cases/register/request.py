from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegisterRequest:
    username: str
    email: str
    password: str = field(repr=False)
