"""System errors detected by the register use case."""


class UnexpectedAccountCreationResult(RuntimeError):
    """Entity factory breached its contract or rejected fixed trusted creation facts."""


class UnexpectedPasswordPolicyDecision(RuntimeError):
    """The domain policy returned a decision outside its declared contract."""
