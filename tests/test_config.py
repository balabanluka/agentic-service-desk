import pytest

from service_desk.config import Settings


def test_default_model_is_luna_and_environment_can_override_it(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert Settings(_env_file=None).openai_model == "gpt-5.6-luna"

    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    assert Settings(_env_file=None).openai_model == "test-model"


def test_knowledge_database_settings_have_safe_v2_defaults(monkeypatch) -> None:
    for name in (
        "DATABASE_URL",
        "OPENAI_EMBEDDING_MODEL",
        "OPENAI_EMBEDDING_DIMENSIONS",
        "KNOWLEDGE_CORPUS_VERSION",
        "KNOWLEDGE_DEFAULT_TOP_K",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url is None
    assert settings.openai_embedding_model == "text-embedding-3-small"
    assert settings.openai_embedding_dimensions == 1536
    assert settings.knowledge_corpus_version == "kb-v1"
    assert settings.knowledge_default_top_k == 4


def test_embedding_dimension_must_match_the_current_vector_schema(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_EMBEDDING_DIMENSIONS", "1024")

    with pytest.raises(ValueError, match="must be 1536"):
        Settings(_env_file=None)
