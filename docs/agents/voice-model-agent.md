# Voice And Model Agent

## Mission

Build the LiveKit agent worker and spoken turn orchestration path. This agent owns push-to-talk turn handling, STT, frame/context selection, prompt assembly, OpenAI-compatible model abstraction, TTS playback through LiveKit, transcript events, timing metrics, and session memory updates.

The goal is to complete the first spoken visual Q&A path before retrieval and then integrate retrieval and safety as structured turn inputs.

## Primary Responsibilities

- Create the separate LiveKit agent worker entrypoint.
- Join LiveKit rooms as the assistant participant.
- Keep LiveKit usage scoped to audio transport.
- Implement provider interfaces:
  - `VisionLanguageModel`
  - `SpeechToTextProvider`
  - `TextToSpeechProvider`
- Implement OpenAI cloud provider adapters for MVP.
- Keep model, STT, and TTS provider-specific details hidden behind interfaces.
- Support later OpenAI-compatible local endpoints through config.
- Implement push-to-talk turn lifecycle:
  - detect start
  - capture audio
  - stop on release or 20-second limit
  - discard empty/no-speech turns
- Run STT and create stable `turn_id` values.
- Request selected frame/context from backend services.
- Assemble model prompt from structured blocks:
  - system/persona
  - session memory
  - user transcript
  - visual frame metadata and image when available
  - retrieved sources
  - safety assessment
- Call the vision-capable model.
- Run post-model safety checks before TTS and transcript finalization.
- Synthesize and play voice responses through LiveKit.
- Emit transcript, response, error, citation, frame-reference, safety, and timing events.
- Update live session memory after each completed turn.

## Owned Repository Areas

- `backend/manfriday/voice_agent/`
- `backend/manfriday/models/`
- prompt assembly utilities
- agent worker entrypoint
- model/STT/TTS mock providers for tests
- turn timing metrics

## Required Interfaces

Provider interfaces:

```text
VisionLanguageModel
  complete_turn(request: ModelTurnRequest) -> ModelTurnResponse

SpeechToTextProvider
  transcribe(audio|stream) -> Transcript

TextToSpeechProvider
  synthesize(text|stream) -> Audio
```

Main turn flow:

1. Detect push-to-talk start from LiveKit/client state.
2. Capture audio until button release or 20-second limit.
3. Run STT.
4. Create `turn_id`.
5. Ask backend service for selected frame.
6. Run retrieval against user text and session context.
7. Run pre-model safety assessment.
8. Assemble prompt with session memory, frame, citations, and safety flags.
9. Call model.
10. Run post-model safety check.
11. Stream or play TTS through LiveKit.
12. Emit transcript, citations, frame reference, timing, and completion events.
13. Update session memory.

## Key Collaboration Points

- Use session, events, and LiveKit room data from the backend control plane agent.
- Use frame selection and frame metadata from the GoPro/frame pipeline agent.
- Use retrieval snippets and safety assessments from the retrieval/safety agent.
- Drive Android listening/thinking/speaking/transcript states through stable events.
- Provide timing data to the QA/release integration agent for latency validation.

## Implementation Phases

Phase 1:

- Agent worker skeleton that can join a LiveKit room.

Phase 3:

- Provider interfaces and mock providers.
- OpenAI-backed MVP providers.
- Push-to-talk turn lifecycle.
- Frame selection at turn time.
- Prompt assembly without retrieval first.
- Transcript and response events.
- TTS response playback through LiveKit.

Phase 4 and later:

- Retrieval context integration.
- Citation events.
- Safety prompt block and post-model safety constraint.
- Debug artifact handoff.
- Timing and reliability hardening.

## Test Responsibilities

- Provider interface tests with mock providers.
- Agent turn orchestration using mocked STT, model, TTS, frame selection, retrieval, and safety services.
- Empty/no-speech turn discard behavior.
- Frame-unavailable behavior.
- Transcript event sequence.
- Timing metric collection.
- Model provider tests using a mock OpenAI-compatible server.

## Acceptance Criteria

- User can ask a spoken visual question and hear a spoken response.
- Transcript shows user text, assistant text, and frame reference.
- If no fresh frame exists, backend proceeds without image and reports degraded visual context.
- Android receives distinct listening, thinking, speaking, completion, and error states.
- Provider config changes do not require Android changes.
- Quick Q&A response starts within the PRD latency target under normal conditions.

## Non-Goals

- Do not implement LiveKit as a product-state transport.
- Do not bypass backend safety checks.
- Do not hard-code OpenAI-specific assumptions into Android-facing contracts.
- Do not send continuous raw video to the model.
