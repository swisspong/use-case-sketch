class InvalidAccessRequirement(RuntimeError):
    """Trusted caller supplied an undeclared requirement; configuration failure."""


class InvalidAccessValidationResult(RuntimeError):
    """Verifier/scope returned undeclared facts, wrong identity or an invalid decision."""
