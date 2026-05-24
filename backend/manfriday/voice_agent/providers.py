from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AudioInput:
    content: bytes
    mime_type: str = "audio/wav"


@dataclass(frozen=True)
class Transcript:
    text: str


@dataclass(frozen=True)
class ModelTurnRequest:
    turn_id: str
    session_id: str
    user_text: str
    frame_id: str | None
    visual_status: str


@dataclass(frozen=True)
class ModelTurnResponse:
    text: str


@dataclass(frozen=True)
class SynthesizedAudio:
    content: bytes
    mime_type: str = "audio/wav"


class SpeechToTextProvider(Protocol):
    def transcribe(self, audio: AudioInput) -> Transcript: ...


class VisionLanguageModel(Protocol):
    def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResponse: ...


class TextToSpeechProvider(Protocol):
    def synthesize(self, text: str) -> SynthesizedAudio: ...


class MockSpeechToTextProvider:
    def __init__(self, text: str = "What am I looking at?") -> None:
        self.text = text

    def transcribe(self, audio: AudioInput) -> Transcript:
        return Transcript(text=self.text)


class MockVisionLanguageModel:
    def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResponse:
        if request.frame_id is None:
            return ModelTurnResponse(
                text=f"I do not have a fresh frame, but I heard: {request.user_text}",
            )
        return ModelTurnResponse(
            text=f"I used frame {request.frame_id} to answer: {request.user_text}",
        )


class MockTextToSpeechProvider:
    def synthesize(self, text: str) -> SynthesizedAudio:
        return SynthesizedAudio(content=text.encode("utf-8"), mime_type="audio/mock")
