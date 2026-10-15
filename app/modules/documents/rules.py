"""Deterministic quality heuristics. No dictionary or language model is consulted."""

from app.modules.documents.text_quality import assess_problem_characters


def assess_quality(text: str, image_percent: float, thresholds: dict[str, int]) -> dict:
    problems = assess_problem_characters(text)
    thai = sum("\u0e01" <= c <= "\u0e5b" for c in text if not c.isspace())
    characters = problems.non_whitespace_count
    quality = {
        "thai_percent": round(100 * thai / characters, 2) if characters else 0,
        "garbled_thai_percent": round(problems.percent, 2),
        "text_chars": characters,
        "image_percent": round(image_percent, 2),
    }
    # Decide with the same values exposed by the API (inclusive boundaries).
    failed = []
    for key, metric, minimum in (
        ("max_thai_percent", "thai_percent", False),
        ("max_garbled_thai_percent", "garbled_thai_percent", False),
        ("min_text_chars", "text_chars", True),
        ("max_image_percent", "image_percent", False),
    ):
        if (
            (quality[metric] < thresholds[key])
            if minimum
            else (quality[metric] > thresholds[key])
        ):
            failed.append(key)
    return quality | {"failed": failed, "passed": not failed}
