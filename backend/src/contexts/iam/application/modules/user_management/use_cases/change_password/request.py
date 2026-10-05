from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChangePasswordRequest:
    current_password: str = field(repr=False)
    new_password: str = field(repr=False)
