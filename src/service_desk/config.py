"""Application configuration loaded from environment variables."""

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-luna"
    database_url: SecretStr | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = Field(default=1536, gt=0)
    knowledge_corpus_version: str = "kb-v1"
    knowledge_default_top_k: int = Field(default=4, ge=1, le=10)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def uses_the_current_embedding_schema_dimensions(self) -> "Settings":
        if self.openai_embedding_dimensions != 1536:
            raise ValueError(
                "OPENAI_EMBEDDING_DIMENSIONS must be 1536 until the pgvector schema is migrated"
            )
        return self
