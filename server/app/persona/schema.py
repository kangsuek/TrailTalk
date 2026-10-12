"""캐릭터 YAML(server/personas/*.yaml) 스키마. 키 오타는 바로 오류로 잡는다(NFR-08)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# 캐시된 객체를 여러 곳이 공유하므로 목록도 바꿀 수 없는 tuple로 둔다
TextList = Annotated[tuple[Text, ...], Field(min_length=1)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SpeechStyle(_Strict):
    # YAML 키는 register(BaseModel 속성과 이름이 겹쳐 내부 이름만 바꾼다)
    register_: Text = Field(alias="register")
    use: TextList
    avoid: TextList
    max_sentences_voice: Annotated[StrictInt, Field(ge=1, le=10)]


class VoiceStyle(_Strict):
    tts_voice: Text
    speaking_rate: Annotated[float, Field(gt=0.25, le=4.0)]
    pitch: Annotated[float, Field(ge=-20, le=20)]  # TTS 피치(반음)


class Persona(_Strict):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]{1,64}$")]
    name: Text
    role: Text
    personality: TextList
    speech_style: SpeechStyle
    brainstorm_style: TextList
    examples: TextList
    voice: VoiceStyle

    @model_validator(mode="after")
    def _placeholder_only_in_examples(self) -> "Persona":
        """{호칭} 자리표시자는 examples에서만 치환되므로 다른 필드에 쓰면 오류로 알린다."""
        data = self.model_dump(exclude={"examples"})
        if "{호칭}" in str(data):
            raise ValueError("{호칭}은 examples에서만 쓸 수 있습니다")
        return self
