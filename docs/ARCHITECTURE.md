# Architecture

## Status and constraints

This document defines the implemented architecture and its gated extensions.
All roadmap technical packages now exist, including a controlled private
single-process deployment, but the live-provider and public-production
acceptance gates in `DECISIONS.md` and `RISKS.md` still apply. Technical
availability is not provider-use or launch approval.

Architectural priorities, in order, are:

1. domain behavior that can be tested without networks or frameworks;
2. replaceable external providers;
3. minimal retention and exposure of copyrighted subtitle text;
4. explicit failure, quota, timeout, and validation behavior; and
5. an incremental path from a local single-process MVP to a public service.

## System context

```text
Browser (React + TypeScript)
          |
          | HTTPS / JSON or multipart upload
          v
FastAPI HTTP adapter
          |
          v
Application use cases
          |
          +-----------------> Domain models and policies
          |
          +---- ports -------+-------------------+
          |                  |                   |
          v                  v                   v
Movie/subtitle adapter   Language analyzer   Transcript session store
(SubDL candidate)        (OpenAI candidate)   (memory in local MVP)
```

The dependency direction points inward. Domain and application modules must not
import FastAPI, HTTPX, SubDL, TMDB, an LLM SDK, or frontend types.

## Repository layout

The intended monorepo layout is:

```text
backend/
  pyproject.toml
  uv.lock
  src/movie_language_helper/
    domain/
    application/
    ports/
    adapters/inbound/http/
    adapters/outbound/srt/
    adapters/outbound/fake_analyzer.py
    adapters/outbound/memory_session_store.py
    infrastructure/
  tests/
    unit/
    integration/
    contract/
    fixtures/
frontend/
  package.json
  package-lock.json
  src/
    api/
    components/
    features/
    pages/
  tests/
docs/
```

The frontend and backend have independent dependency manifests, test commands,
and build outputs. A root task runner may orchestrate them but must not merge
their source trees.

## Backend layers

### Domain

Pure typed Python representing values, invariants, and policies described in
`DATA_MODEL.md`. It owns:

- timestamps and interval overlap;
- subtitle cue and transcript invariants;
- text normalization rules that are product behavior;
- analyzer-result validation and deduplication;
- learning-item ranking; and
- stable domain error categories.

The domain has no I/O and uses no Pydantic models. Frozen dataclasses, enums,
and small pure functions are preferred.

### Application

Use cases coordinate domain objects and ports:

- `SearchMovies`;
- `ListSubtitleCandidates`;
- `CreateProviderTranscriptSession`;
- `CreateUploadedTranscriptSession`;
- `PreviewTranscriptSession`;
- `AnalyzeInterval`; and
- `DeleteTranscriptSession`.

Application services define transaction/cleanup boundaries and translate port
failures into stable application errors. They do not know HTTP status codes.

### Ports

Ports are small typed `Protocol` interfaces using internal models only:

- `MovieCatalog.search(query, year, limit) -> list[MovieMatch]`;
- `SubtitleCatalog.list(movie, language) -> list[SubtitleCandidate]`;
- `SubtitleSource.fetch(candidate) -> SubtitlePayload`;
- `SubtitleParser.parse(payload) -> Transcript`;
- `TranscriptSessionStore.put/get/delete(...)` with a TTL;
- `LanguageAnalyzer.analyze(AnalysisInput) -> AnalyzerResult`;
- `Clock.now()` and `IdGenerator.new()` where deterministic tests need them.

Movie search and subtitle retrieval are separate capabilities even when one
external service implements both. This prevents a future catalog change from
changing transcript acquisition semantics.

### Adapters and infrastructure

Inbound HTTP models are Pydantic models and map explicitly to domain values.
Outbound adapters map provider payloads to internal models and own provider
authentication, schemas, timeouts, rate-limit headers, and error translation.

Long-lived HTTP clients are created and closed in application lifespan. Each
provider has explicit connect/read/write/pool timeouts, connection limits, and
bounded retry rules. Retry only idempotent reads and honor `Retry-After`; do not
automatically repeat an LLM request after an ambiguous response because that can
duplicate cost.

## Primary runtime flow

### Transcript preparation

1. Accept either a provider subtitle reference or an SRT upload; never accept an
   arbitrary download URL from the browser.
2. Enforce request and content-length limits while streaming bytes.
3. For archives, inspect members before reading any file. Reject traversal,
   symlinks, encrypted entries, nested archives, excessive entry counts,
   excessive uncompressed size, and unsupported formats.
4. Select a single English SRT deterministically or return an ambiguity error.
5. Decode with a bounded, documented fallback policy and return warnings when
   the encoding is uncertain.
6. Parse into domain cues, normalize safe presentation text, validate ordering
   and timestamps, and compute a content digest.
7. Store the parsed transcript in a short-lived session and discard download or
   upload bytes as soon as parsing finishes.

Raw provider subtitles must not be persisted or cached beyond the request until
provider caching and downstream-processing rights are confirmed. The local MVP
session store contains parsed cues in memory and therefore supports only one
process. A distributed encrypted store is a later adapter, not an MVP
assumption.

### Preview and synchronization

The client requests a bounded preview around a playback time. It never receives
the full transcript. `sync_offset_ms` is applied as:

```text
display_time = subtitle_time + sync_offset_ms
```

A positive offset displays subtitle cues later; a negative offset displays them
earlier. Interval extraction compares adjusted cue times with the user's
playback interval. The offset is immutable input to an analysis result so the
result is reproducible.

### Language analysis

1. Validate the interval and session ownership/existence.
2. Extract overlapping cues with a small configurable context window, while
   keeping the analysis interval distinct from context-only cues.
3. Remove unsupported markup and obvious non-dialogue annotations according to
   deterministic, tested rules.
4. Send only the required cues and learner settings through the
   `LanguageAnalyzer` port.
5. Treat all subtitle text as untrusted data, not instructions. LLM adapters use
   no tools for this operation and request strict structured output.
6. Validate the returned schema again locally. Verify every cue reference and
   that each quoted expression occurs in the referenced normalized cue.
7. Normalize, deduplicate, rank, and cap the result in the domain.
8. Return provider-neutral result metadata including analyzer name, model
   identifier, prompt/schema version, latency, and token usage when available.

Invalid analyzer output is an explicit analyzer failure or a bounded repair
attempt, never partially trusted data silently returned to the user.

## HTTP API boundary

All product endpoints are versioned under `/api/v1`. Exact implemented schemas
are generated by FastAPI and locked by integration contract tests.

```text
POST   /api/v1/transcript-sessions/upload
POST   /api/v1/transcript-sessions/provider
GET    /api/v1/transcript-sessions/{id}/preview?at_ms=&sync_offset_ms=
DELETE /api/v1/transcript-sessions/{id}
POST   /api/v1/analyses
GET    /api/v1/capabilities
GET    /api/v1/movies?q=&year=&limit=
GET    /api/v1/movies/{id}/subtitles?limit=
GET    /health/live
GET    /health/ready
GET    /metrics
```

Movie search, provider subtitle listing, and provider-session creation are
registered but return `provider_disabled` unless the fail-closed SubDL startup
gate is fully configured. Capabilities let the frontend hide unavailable
provider controls while preserving upload fallback. This is not release
approval: `ADR-004` remains provisional.

There are deliberately no public `get full transcript` or arbitrary `slice
transcript` endpoints. Analysis accepts a transcript-session ID, interval,
offset, learner level, and result limit. The MVP request is synchronous. If
observed latency requires asynchronous work, add an `AnalysisJobStore` port and
durable worker before returning `202`; FastAPI in-process background tasks are
not a durable job queue.

Errors use one envelope with a stable machine-readable code, a safe message, an
optional retry hint, and a correlation ID. Provider response bodies and secrets
are never forwarded.

## Frontend architecture

Use React with TypeScript and Vite as a client-side application. Organize state
by product feature rather than by generic file type. Server state and workflow
state remain distinct; provider secrets never enter the browser bundle.

The first workflow is an explicit state machine:

```text
movie search -> movie selected -> subtitle/session ready
             -> timing checked -> interval valid -> analyzing -> result/error
```

The interface must make expired sessions, subtitle ambiguity, synchronization,
provider quota, and retryable failures visible. Accessibility requirements
include keyboard operation, semantic form labels, focus management on state
changes, and non-color-only error/status indicators.

## Configuration and secrets

Configuration is loaded once at startup into a typed settings object. Required
secrets depend on enabled adapters:

- `SUBDL_API_KEY` for the SubDL adapter;
- `OPENAI_API_KEY` for the OpenAI adapter; and
- no TMDB secret unless the TMDB decision gate is cleared.

Provider base URLs, selected analyzer model, timeouts, maximum file/archive
sizes, interval limit, session TTL, allowed CORS origins, and feature flags are
configuration. Secrets must not be committed, logged, included in URLs when a
header is supported, or returned in diagnostics.

Startup fails clearly when an enabled adapter lacks required configuration.
The private profile reads separate edge-to-backend bearer and browser Basic-auth
hash secrets from files. Caddy terminates TLS and injects the backend bearer;
the backend remains unexposed and independently checks trusted hosts, exact
CORS origins, body limits, authentication, and its process-local rate limit.

### Initial safety defaults

These are provisional, configuration-backed defaults for the first vertical
slice. Tests lock their semantics; change values only after the parser, timing,
and cost spikes provide evidence.

| Setting | Initial default |
| --- | ---: |
| Raw SRT upload | 2 MiB |
| Provider/archive compressed response | 10 MiB |
| Archive total declared uncompressed bytes | 20 MiB |
| Archive member count | 100 |
| Archive compression ratio per selected member | 100:1 |
| Transcript cue count | 20,000 |
| Transcript normalized characters | 2,000,000 |
| Normalized characters per cue | 10,000 |
| Transcript session TTL | 30 minutes |
| In-memory session capacity | 100 sessions |
| Preview | 15 seconds each side, at most 20 cues |
| Absolute synchronization offset | 10 minutes |
| Analysis interval | 10 minutes |
| Adjacent context | at most 2 cues each side, within 30 seconds of the interval |
| Learning items | 12 default, 30 maximum |
| Whole request | 11 MiB |
| Private client rate | 120 requests per 60 seconds |

Reject on a limit before fully buffering or expanding input. Server-wide and
per-client concurrency limits remain a public-deployment decision.

## Security and data handling

- Subtitle files, archive metadata, provider payloads, and LLM output are
  untrusted input.
- Uploaded/provider files have byte, cue-count, text-length, and processing-time
  limits.
- Archive handling reads approved members without extracting an archive tree to
  disk.
- HTML/ASS markup is converted to plain text before browser rendering; React
  must not use raw HTML for subtitle content.
- API requests cannot select arbitrary upstream hosts, preventing SSRF.
- Logs contain IDs, sizes, timings, and error categories, not subtitle text,
  prompts, analysis content, or API keys.
- Default LLM requests are stateless and explicitly disable provider-side
  response storage where the adapter supports it. Provider abuse-monitoring
  retention can still apply and must be disclosed.
- Public deployment requires authentication or abuse-resistant anonymous
  sessions, per-client rate limits, upload limits, CSRF/CORS review, TLS, and a
  deletion/retention policy. The local MVP alone is not public-production ready.

## Observability

Use structured logs with correlation IDs and metrics for request count/latency,
provider latency/error/quota state, parse failures, session expiry, analysis
failures, analyzer token usage, and estimated cost. Do not use movie title or
subtitle text as metric labels.

Readiness checks validate local configuration and required local resources;
they do not spend quota by calling every provider on each probe.

The implemented process registry exposes Prometheus text on authenticated
`/metrics`: normalized-route/status request counters, aggregate duration,
stable error codes, analysis latency/count, and analyzer token totals. It has no
content, client, session, movie, or expression labels. Sample alerts/dashboard
are under `deploy/observability`. Process-local telemetry resets at restart and
must be replaced/scraped into shared storage for scaled operation.

## Testing strategy

- Unit tests: all domain invariants, interval boundaries, offset semantics,
  normalization, deduplication, and ranking.
- Parser tests: licensed/synthetic fixtures covering BOMs, line endings,
  overlapping cues, multiline text, markup, malformed timestamps, and limits.
- Adapter contract tests: HTTP transports mocked at the boundary with scrubbed
  provider fixtures, including quota, timeout, malformed response, and schema
  drift cases.
- API integration tests: dependency overrides supply fake ports; no network is
  required.
- Analyzer contract tests: strict schema, refusal/incomplete output, invalid cue
  references, and untrusted-text prompt-injection cases.
- Quality evaluation: a small versioned, legally usable golden set scored for
  precision, usefulness, duplicates, and unsupported claims. Model or prompt
  changes must run it.
- Frontend tests: workflow states, accessibility-critical behavior, API errors,
  and one end-to-end happy path against a fake backend.

Live provider smoke tests are opt-in, use dedicated credentials, and are never
part of the default unit-test command.

## Deployment evolution

The implemented Compose profile is one non-root, read-only backend process plus
a Caddy static/TLS edge with Basic authentication and an internal bearer. It
uses an in-memory transcript-session store and process-local rate/metric state,
so it is suitable only for local or controlled private evaluation. Before
horizontal scaling, provide authenticated ownership, a shared encrypted TTL
session store, distributed limits/budgets, and explicit deletion behavior. Add
a durable job queue only if measured analysis latency requires asynchronous
jobs, and relational persistence only for a confirmed durable account/history
requirement. See `DEPLOYMENT.md`, `OPERATIONS.md`, and `THREAT_MODEL.md`.
