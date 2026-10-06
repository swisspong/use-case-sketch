"""Unexpected inner-layer decisions, not ordinary password rejections."""


class UnexpectedPasswordChangeDecision(RuntimeError):
    """Account validation/transition violated its declared decision contract."""
