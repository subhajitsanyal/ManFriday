# Retrieval, Safety, And Debug Agent

## Mission

Build the grounding, safety, and diagnostic layers for Man Friday. This agent owns local/configured-source retrieval, optional web fallback, citation metadata, deterministic DIY safety policy, debug artifact persistence, and secret redaction.

The product depends on this agent to keep answers sourced, cautious around hazardous work, and debuggable without storing unnecessary private data.

## Primary Responsibilities

- Implement ingestion for local documents and configured online URLs.
- Load existing indexes on startup without automatically re-indexing every time.
- Provide both CLI and authenticated REST ingestion paths.
- Implement source-aware chunking and metadata.
- Implement hybrid retrieval from day one:
  - BM25 keyword index
  - SentenceTransformers embeddings
  - FAISS vector store
  - merge/rerank
- Prefer local docs over configured online resources when scores are close.
- Prefer manufacturer/manual sources over generic sources when scores are close.
- Implement optional Tavily web search fallback.
- Keep web search disabled by default.
- Label and cite web search results when used.
- Implement safety checks at three stages:
  - after STT and before retrieval/model call
  - after retrieval/frame context and before model call
  - after model response and before TTS/transcript finalization
- Detect high-risk DIY categories:
  - live electrical work
  - gas lines
  - structural/load-bearing changes
  - hazardous chemicals
  - power tools and blades
  - ladders/heights
  - heat/fire
- Provide response constraints and user-visible warnings.
- Implement debug mode endpoint behavior and artifact writer.
- Redact API keys, auth headers, local secret, Wi-Fi password, and other sensitive values.
- Keep only targeted debug artifacts and last 10 debug sessions by default.

## Owned Repository Areas

- `backend/manfriday/retrieval/`
- `backend/manfriday/safety/`
- `backend/manfriday/debug/`
- `backend/manfriday/memory/` in coordination with the voice/model agent
- `knowledge/local-docs/`
- `knowledge/online-sources/sources.yaml`
- `backend/indexes/`
- `backend/debug_artifacts/`
- retrieval, safety, and redaction tests

## Required Interfaces

Retrieval submodules:

```text
retrieval/
  loaders
  chunking
  bm25
  vectors
  ranking
  web
  metadata
```

REST endpoints:

- `POST /retrieval/ingest`
- `POST /debug/mode`

Events:

- `retrieval.sources.selected`
- `safety.warning`
- `debug.mode.changed`

Safety output:

```text
SafetyAssessment
  risk_level: low | moderate | high
  categories: list[str]
  flags: list[str]
  response_constraint: none | caution | refuse_detailed_instruction
  user_visible_warning
```

Debug artifact structure:

```text
backend/debug_artifacts/
  session_<session_id>/
    manifest.json
    transcript.jsonl
    frames/
      <frame_id>.jpg
    retrieval/
      <turn_id>.json
    model/
      <turn_id>.json
    events.jsonl
    timings.jsonl
```

## Key Collaboration Points

- Use backend auth and error helpers from the backend control plane agent.
- Provide retrieval snippets and source IDs to the voice/model agent for prompt assembly.
- Provide citation metadata and web-search-used state to the Android client agent.
- Consume frame metadata and selected analysis frames from the GoPro/frame pipeline agent for debug artifacts.
- Provide safety flags to session memory and Android-visible events.
- Coordinate eval scenarios and failure cases with the QA/release integration agent.

## Implementation Phases

Phase 4:

- Source/chunk metadata schema.
- Markdown/text ingestion.
- PDF ingestion with page limits.
- Configured URL ingestion from YAML.
- BM25 index.
- SentenceTransformers embeddings and FAISS persistence.
- Merge/rerank with source priority rules.
- Retrieval context in prompt assembly.
- Citation events and Android citation rendering support.

Phase 4a:

- Tavily client.
- Web search timeout and max-result limits.
- Low-confidence web fallback rules.
- Web citation normalization.

Phase 5:

- Safety rules and prompt block.
- Post-response safety checker.
- Debug mode and artifact writer.
- Redaction.
- Timing and diagnostic artifacts.

## Test Responsibilities

- Retrieval ingestion over fixture markdown, text, PDF, and configured URLs.
- Local test HTTP server for URL ingestion failures and limits.
- Ranking merge behavior and source preference rules.
- Web fallback trigger behavior with mocked Tavily responses.
- Safety category detection and response constraints.
- Post-model response checker behavior.
- Debug artifact writing and retention.
- Redaction tests for secrets, auth headers, API keys, and Wi-Fi password.

## Acceptance Criteria

- `manfriday ingest` builds local/configured-source indexes.
- `POST /retrieval/ingest` returns a per-source summary with skipped and failed items.
- Agent responses include citations when retrieved context is used.
- Web search is off by default and clearly labeled when enabled and used.
- High-risk prompts are constrained according to policy.
- Debug mode saves targeted artifacts only.
- Secrets never appear in debug artifacts, logs, transcripts, or model metadata.

## Non-Goals

- Do not recursively crawl websites for MVP.
- Do not perform live allowed-domain search beyond the optional Tavily fallback.
- Do not persist project memory across days.
- Do not save every sampled frame or continuous audio.
