import yaml

from app.config import settings

REQUIRED_KEYS = {"id", "name", "role", "personality", "speech_style", "brainstorm_style", "voice"}


def test_default_persona_file_has_required_keys():
    path = settings.persona_dir / f"{settings.default_persona}.yaml"
    persona = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert REQUIRED_KEYS <= persona.keys()
    assert persona["id"] == settings.default_persona
    assert persona["speech_style"]["max_sentences_voice"] > 0
