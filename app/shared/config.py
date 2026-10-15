from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-to-a-long-random-secret-at-least-32b"
    # module settings: <module>_<name>
    text_quality_default_max_thai_percent: int = Field(default=50, ge=0, le=100)
    text_quality_default_max_garbled_thai_percent: int = Field(default=5, ge=0, le=100)
    text_quality_default_min_text_chars: int = Field(default=50, ge=0)
    text_quality_default_max_image_percent: int = Field(default=80, ge=0, le=100)
    # llm_config: encrypts saved API keys. Changing it makes existing keys unreadable.
    llm_config_api_key_secret: str = "change-me-to-a-long-random-secret-for-api-keys"
    documents_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    documents_parse_timeout_seconds: float = Field(default=30, gt=0)
    # Total provider deadline for OCR of one page, both passes (Penpot said 60 s; raised
    # to 90 s because transcribe + structure takes ~58 s, see docs/ocr-table-structure-experiment.md).
    documents_ocr_timeout_seconds: float = Field(default=90, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
