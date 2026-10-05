"""Legacy registration comparison contract; UserAccount owns the shared rule.

Retained at its original path for compatibility; no independent password rule.
"""

from enum import Enum, auto

from contexts.iam.domain.identity.username import Username
from contexts.iam.domain.identity.user_account import InvalidAccountDecisionFacts, UserAccount

from contexts.iam.domain.identity.value_objects import InvalidRegistrationValue, Password


class PasswordUsernameDecision(Enum):
    DISTINCT = auto()
    MATCHES_USERNAME = auto()


class RegistrationPasswordPolicy:
    @staticmethod
    def compare_to_username(username: Username, password: Password) -> PasswordUsernameDecision:
        """Compare without altering the password that will be hashed."""
        result = UserAccount.validate_password(username=username, raw=password.value)
        if isinstance(result, InvalidRegistrationValue):
            return PasswordUsernameDecision.MATCHES_USERNAME
        if isinstance(result, Password):
            return PasswordUsernameDecision.DISTINCT
        raise InvalidAccountDecisionFacts("Undeclared account password decision")
