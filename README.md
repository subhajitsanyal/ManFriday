# Man Friday

Man Friday is a hands-free visual copilot for DIY work. The system uses a GoPro
as a workbench camera, an Android app for voice interaction, a self-hosted
LiveKit stack for realtime conversation, and a Mac backend for GoPro control,
frame sampling, retrieval, and OpenAI-compatible model calls.

## Repository Layout

```text
ManFriday/
  android/                    Android app source will live here.
  backend/                    Mac backend, LiveKit agent, GoPro/frame pipeline.
  docs/
    product/                  PRD and product decisions.
    engineering/              Architecture/specs/API contracts.
    research/                 Framework notes and implementation research.
  knowledge/
    local-docs/               User-provided manuals, notes, PDFs, etc.
    online-sources/           Lists/config for trusted online resources.
```

## Current Status

The current focus is requirements and architecture. Existing GoPro exploration
code has been moved to:

```text
../MiscExplorations/
```

The first implementation priority is the GoPro/frame pipeline, followed by an
end-to-end thin slice.
