"""Pure field validation; no I/O."""

from app.modules.text_quality.errors import ThresholdOutOfRange


def check_thresholds(changes: dict[str, int | float]) -> None:
    for field, value in changes.items():
        if (
            not float(value).is_integer()
            or value < 0
            or (field != "min_text_chars" and value > 100)
        ):
            raise ThresholdOutOfRange(field=field)
