"""Pure normalization and validation."""

from urllib.parse import urlsplit

from app.modules.llm_config.errors import PresetInvalid

MAX_LENGTH = {"name": 80, "model_id": 200, "base_url": 500, "api_key": 500}


def clean_preset_fields(fields: dict[str, str]) -> dict[str, str]:
    cleaned = {}
    for field, raw in fields.items():
        value = raw.strip()
        if not 1 <= len(value) <= MAX_LENGTH[field]:
            raise PresetInvalid(field=field)
        if field == "base_url":
            try:
                url = urlsplit(value)
                valid = (
                    url.scheme in ("http", "https")
                    and bool(url.hostname)
                    and not url.username
                    and not url.password
                    and not url.query
                    and not url.fragment
                    and not any(c.isspace() for c in value)
                )
                _ = url.port  # Parsing rejects invalid ports.
            except ValueError:
                valid = False
            if not valid:
                raise PresetInvalid(field=field)
            value = value.rstrip("/")
        cleaned[field] = value
    return cleaned
