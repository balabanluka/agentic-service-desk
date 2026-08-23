from service_desk.config import Settings


def test_default_model_is_luna_and_environment_can_override_it(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert Settings(_env_file=None).openai_model == "gpt-5.6-luna"

    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    assert Settings(_env_file=None).openai_model == "test-model"
