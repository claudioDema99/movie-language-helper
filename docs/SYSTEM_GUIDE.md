# System guide

## What the system is—and is not

Movie Language Helper prepares a small study list for a chosen scene of an
English-language movie. A learner supplies an English SRT, checks whether its
timestamps match their copy of the movie, selects a playback interval and CEFR
level, and receives grounded vocabulary/expression candidates.

The repository is deliberately fail-closed:

- local/default mode parses, previews, and exercises the complete API/UI, but
  its `FakeLanguageAnalyzer` returns an empty candidate set;
- useful automatic explanations require an approved live analyzer adapter;
- SubDL search/download and OpenAI analysis are implemented but disabled until
  their legal, privacy, contract, quality, and model-selection gates close; and
- the provided server deployment is private, authenticated, and single-process,
  not a public SaaS architecture.

This distinction matters: successful installation does not silently authorize
third-party subtitle or LLM processing.

## End-to-end runtime flow

### 1. Browser startup

`frontend/src/main.tsx` mounts the single React `App` into `#root` and imports
the stylesheet. `App` requests `/api/v1/capabilities`. If that request fails, it
falls back to upload-only controls. Provider search is shown only when the
backend says the gated provider is active.

### 2. Transcript acquisition

For upload, the browser requires a `.srt` file and rights acknowledgement, then
sends multipart form data to `/api/v1/transcript-sessions/upload`. The HTTP
adapter checks filename/format and reads chunks only up to the configured byte
limit. The parser:

1. accepts only non-empty SRT under the byte limit;
2. decodes strict UTF-8 (including BOM), then CP-1252 as a warned fallback;
3. normalizes line endings and structurally validates every SRT block;
4. lets `pysubs2` parse timestamps/text;
5. strips/sanitizes markup, whitespace, speaker/non-dialogue representation;
6. enforces cue, per-cue, and total-character limits; and
7. creates immutable cues plus a SHA-256 digest of the original bytes.

The upload bytes then fall out of scope. `CreateUploadedTranscriptSession`
creates a cryptographically random ID, adds a UTC expiry (30 minutes by
default), and places the parsed transcript in the bounded in-memory store. When
capacity is reached, the store removes expired entries and then evicts the
oldest inserted session.

When approved provider mode is enabled, the browser instead searches movies,
explicitly chooses a SubDL movie and release, and posts the chosen subtitle ID.
The backend—not the browser—follows only HTTPS download locations on an
allowlist. A bounded ZIP reader selects exactly one safe SRT member without
extracting a directory, then sends those bytes through the same parser/session
path.

### 3. Timing preview

The learner enters a movie playback timestamp and signed offset. The convention
is exact:

```text
display timestamp = subtitle timestamp + sync_offset_ms
```

A negative value moves cues earlier; a positive value moves them later. The
preview use case selects at most 20 cues in a ±15-second window and returns only
sanitized cue text. It never exposes the whole transcript. One global offset
corrects a constant release shift but cannot correct progressive/frame-rate
drift; the user must choose a better matching release in that case.

### 4. Scene analysis

The browser validates a positive interval no longer than ten minutes and posts
the session ID, interval, offset, CEFR, and optional result limit. The
`AnalyzeInterval` use case:

1. checks the interval, offset, item limit, session status, and TTL;
2. selects half-open-overlapping dialogue cues after applying the offset;
3. adds at most two nearby context cues per side within 30 seconds and marks
   them `context_only`;
4. sends only those cues and learner settings through `LanguageAnalyzer`, once,
   under the overall timeout;
5. treats all returned candidates as untrusted;
6. requires every cited cue to exist and the normalized expression to occur in
   it; a candidate found only in context cues is rejected;
7. removes noise and deduplicates by normalized form, type, and contextual
   meaning, merging unique occurrences;
8. assigns a deterministic relevance score and caps the ordered list; and
9. creates a content-hiding fingerprint and safe provenance metadata.

Ranking version `ranking-v2` weights analyzer salience 50%, confidence 30%, and
learner-relative difficulty 20%. CEFR influences difficulty only at confidence
≥0.6; otherwise it uses a neutral value. Each additional occurrence adds 0.02,
up to 0.08, and the final score is clamped to 0..1 and quantized to 0.001.
Ties sort by normalized form and type. Timestamps/excerpts always come from
local cues, never from analyzer assertions.

### 5. Response and cleanup

The API maps domain/application results to stable snake-case JSON. Transcript
and analysis routes use `Cache-Control: no-store`; errors share `{error: {code,
message, retryable, correlation_id}}`. A replaced session is deleted on a
best-effort basis by the browser. Explicit DELETE, TTL lookup/cleanup, capacity
eviction, or backend restart removes it; there is no database or transcript
backup.

## Backend component reference

### Domain: pure rules, no I/O

- `domain/time.py` defines non-negative `Timestamp`, positive half-open
  `TimeRange`, and signed `SyncOffset`, including overlap and zero-clamped
  display conversion.
- `domain/normalization.py` converts ASS/HTML-ish subtitle presentation into
  safe plain `source_text`, stricter `analysis_text`, cue flags, and a
  Unicode/case/whitespace-normalized matching form.
- `domain/subtitle.py` defines cue/source/warning enums, resource limits,
  `SubtitleCue`, and `Transcript`. Transcript construction sorts/validates cues,
  enforces total bounds, and exposes derived duration.
- `domain/session.py` defines an immutable UTC-aware `TranscriptSession` and its
  expiry predicate.
- `domain/movie.py` defines provider-scoped `ExternalId`, `MovieMatch`, and
  `SubtitleCandidate`; no provider ID is canonical across services.
- `domain/extraction.py` implements primary interval and adjacent-context cue
  selection while preserving `context_only` provenance.
- `domain/analysis.py` contains CEFR/item enums, analyzer input/output and final
  result records, candidate validation, grounding, noise filtering,
  deduplication, ranking-v2, stable item IDs, and the reproducibility
  fingerprint.
- `domain/errors.py` is the stable family of domain validation, resource,
  subtitle, interval, and analyzer-output errors.

### Ports: replaceable contracts

- `ports/subtitle.py` contracts `SubtitlePayload` and `SubtitleParser`.
- `ports/session.py` contracts the TTL store and distinguishes found, expired,
  missing, and capacity-eviction outcomes.
- `ports/analyzer.py` contracts one provider-neutral analysis call and its
  bounded failure taxonomy.
- `ports/catalog.py` separately contracts movie search, subtitle listing, and
  subtitle fetch, plus quota-aware provider failures.
- `ports/runtime.py` abstracts the clock and ID generator for deterministic
  tests.

### Application: orchestration

- `application/transcripts.py` parses/stores uploads, builds bounded previews,
  deletes/cleans sessions, resolves expiry versus absence, and exposes only
  warning codes.
- `application/analysis.py` validates a request, extracts cues, applies the
  timeout, maps analyzer failures, invokes domain grounding/ranking, and builds
  final IDs/provenance.
- `application/catalog.py` validates search/list bounds, narrows optional year
  locally, translates provider failures, and funnels provider bytes through the
  normal transcript-session creator.
- `application/errors.py` carries safe application-facing code/message/retry
  information without HTTP coupling.

### Outbound adapters

- `adapters/outbound/srt/parser.py` is the bounded `pysubs2` SRT adapter and
  decoding/malformed-block policy described above.
- `adapters/outbound/memory_session_store.py` uses an async lock and dictionary
  for atomic TTL lookup, delete, cleanup, and deterministic capacity eviction.
- `adapters/outbound/fake_analyzer.py` supplies deterministic metadata and, by
  default, no candidates. Tests can inject outputs/failures without a network.
- `adapters/outbound/openai_analyzer.py` serializes minimal cue JSON, sends fixed
  developer instructions to the configured exact Responses API model with
  strict JSON Schema, `store=false`, no tools, bounded tokens/timeout, and maps
  refusal/incomplete/rate/network/status/schema failures. SDK automatic retries
  are disabled in composition.
- `adapters/outbound/subdl.py` implements the three provider ports over defensive
  v2 DTOs, English/movie filters, HTTPS location allowlisting, streamed download
  limits, one retry for transient idempotent reads, and stable quota/errors.
- `adapters/outbound/safe_zip.py` inspects ZIP metadata, rejects traversal,
  absolute paths, links/devices, encryption, nesting, excessive count/expanded
  bytes/ratio, and ambiguity, then reads only the selected SRT member.

### Infrastructure and HTTP

- `infrastructure/config.py` loads frozen `MLH_` settings, optionally reads
  mounted secret files, checks all cross-setting safety relationships, and
  fails startup for incomplete provider/private opt-ins.
- `infrastructure/runtime.py` implements aware UTC time and secure opaque IDs.
- `infrastructure/container.py` is the composition root: it creates the parser,
  store, use cases, metrics, fake or OpenAI analyzer, optional SubDL client, and
  lifespan closers. This is the only place that chooses concrete adapters.
- `infrastructure/security.py` provides strict bearer parsing, constant-time
  comparison, hashed client identity, and the one-process fixed-window limiter.
- `infrastructure/metrics.py` aggregates content-free counters/sums and renders
  Prometheus 0.0.4 text. Dynamic movie/session path segments are normalized
  before becoming labels.
- `adapters/inbound/http/app.py` creates FastAPI, lifecycle cleanup, strict host
  and CORS middleware, rate limiter, exception handlers, and all routers.
- `adapters/inbound/http/middleware.py` assigns/sanitizes request IDs, rejects
  oversized declared bodies, authenticates/rate-limits the private routes, adds
  cache/security headers, and logs/records metadata-only completion/rejection.
- `adapters/inbound/http/schemas.py` contains every Pydantic request/response
  model and the stable camel-free API serialization contract.
- `adapters/inbound/http/transcripts.py` owns multipart upload, bounded chunk
  reads, preview mapping, and deletion routes.
- `adapters/inbound/http/analyses.py` maps analysis JSON to domain values and
  maps final items/provenance back to JSON while recording safe analyzer usage.
- `adapters/inbound/http/catalog.py` exposes capabilities/search/list/provider
  session endpoints and returns `provider_disabled` when adapters are absent.
- `adapters/inbound/http/health.py` exposes non-provider liveness/readiness and
  protected content-free metrics.
- `adapters/inbound/http/errors.py` turns validation/application failures into
  safe status codes/envelopes and error counters.
- `adapters/inbound/http/dependencies.py` retrieves the lifespan-owned
  `AppServices` container from application state.

### Evaluation and scripts

- `evaluation/harness.py` runs analyzer outputs against legal `GoldenCase`
  expectations and computes precision, recall, useful-top-N, duplicates,
  unsupported items, latency, tokens, optional cost, and threshold pass/fail.
- `scripts/validate_golden_corpus.py` schema-checks the six authored cases,
  unique IDs, all A1–C2 levels, grounded expected/distractor strings, and corpus
  version. `evaluation/LICENSE.md` records fixture provenance constraints.
- `scripts/performance_smoke.py` generates a maximum 20,000-cue SRT in memory,
  parses it with production limits, extracts a maximum ten-minute interval, and
  enforces 10-second parse/2-second extraction ceilings.
- `scripts/dependency_licenses.py` reads installed Python distribution metadata,
  fails if a license cannot be identified, and prints the review inventory.

## Frontend component reference

- `src/App.tsx` is the current single feature component. Its state represents
  capabilities, acquisition choice, session, timing, learner inputs,
  pending/error/result states, and provider selections. Starting a request
  aborts the prior request; changing upload/timing invalidates dependent state;
  focus moves to the live status region after important changes. JSX provides
  native labels/controls, explicit rights and AI limitations, release metadata,
  retry guidance, ranked item cards, occurrences, and provenance.
- `src/api/types.ts` mirrors the checked API shapes for capabilities, sessions,
  preview, providers, requests, learning items, and provenance.
- `src/api/client.ts` is the only fetch boundary. It uses relative same-origin
  URLs, `no-store`, same-origin credentials, 25-second timeout plus caller
  cancellation, URL encoding, multipart/JSON bodies, and safe stable error
  parsing with a non-leaking fallback.
- `src/styles.css` supplies responsive panel/card layout, visible focus/error/
  success states, readable typography, and reduced-motion behavior.
- `src/main.tsx` mounts React; `src/vite-env.d.ts` provides Vite TypeScript
  declarations; `index.html` supplies the root and module entry.
- `vite.config.ts` configures React, proxies development `/api` requests to the
  FastAPI service on `127.0.0.1:8000`, and defines Vitest's
  jsdom/setup/exclusions;
  `eslint.config.js` applies typed React/TypeScript lint rules; `tsconfig.json`
  enables strict compilation.
- `src/App.test.tsx` exercises workflow, validation, states, provider controls,
  accessibility-critical focus/labels, and errors with a fake `ApiClient`.
  `src/api/client.test.ts` checks request/error/abort contracts.
- `e2e/upload-analysis.spec.ts` intercepts API calls in a real Chromium page,
  completes upload→preview→analysis, and runs axe WCAG A/AA scans before and
  after results. It proves browser integration, not live-provider behavior.
- `scripts/dependency-licenses.mjs` walks the installed npm graph and prints
  name/version/license, failing unknown licenses.

## Build, deployment, and automation files

- `Makefile` is the root command interface: locked installs, dev servers,
  backend/frontend/full checks, browser installation, corpus/performance gates,
  dependency inventory/licenses/audit, and CycloneDX SBOM generation.
- `.github/workflows/ci.yml` reproduces locked backend and frontend gates on
  pushes/pull requests.
- `backend/Dockerfile` builds a locked Python virtual environment, copies only
  runtime source, runs as UID 10001, health-checks the API, and starts exactly
  one Uvicorn worker.
- `frontend/Dockerfile` builds static Vite assets in Node and copies only `dist`
  plus Caddy configuration into the runtime image.
- `frontend/deploy/docker-entrypoint.sh` reads the internal bearer and Basic-auth
  hash from mounted secrets and then replaces itself with Caddy.
- `frontend/deploy/Caddyfile` performs TLS/static SPA serving, edge Basic auth,
  API reverse proxying with internal bearer injection, compression, and browser
  security headers.
- `compose.yaml` joins the two hardened containers, mounts secrets, keeps the
  backend private/read-only/capability-free, persists only Caddy operational
  state, and health-orders startup. `compose.providers.yaml` is the explicit
  gated provider overlay.
- `deploy/observability/*` supplies Prometheus alert and Grafana dashboard
  templates; `docs/DEPLOYMENT.md` and `docs/OPERATIONS.md` are the deploy,
  rollback, incident, outage, deletion, and takedown runbooks.

## How to use the system

### Local development/evaluation

1. Install Python 3.12+, uv 0.12.6, Node 22.23.2/npm 10.9.8, and Chromium
   prerequisites.
2. Run `make bootstrap`, then `make check`.
3. In separate terminals run `make backend-dev` and `make frontend-dev`.
4. Open `http://127.0.0.1:5173`.
5. Select a legally usable English `.srt`, acknowledge rights, and prepare it.
6. Enter a time near a known line. Adjust milliseconds until preview cues match
   movie playback; negative means earlier, positive later.
7. Enter a ≤10-minute scene, choose CEFR, and analyze.

With default configuration step 7 correctly returns no items because the fake
analyzer is intentionally empty. Use tests/evaluation fixtures to exercise
ranked results. Do not enable a live adapter until its documented gates are
accepted.

### Controlled private server

Follow `docs/DEPLOYMENT.md`: create separate backend bearer and browser Basic
auth secrets, configure exact HTTPS host/origin/site values, build/start Compose,
sign in at the HTTPS URL, and perform the same learner workflow. Operations,
monitoring, deletion, outage, incident, and rollback procedures are in
`docs/OPERATIONS.md`.

### Useful verification commands

```text
make backend-check             backend lock, format, lint, types, 100% tests
make frontend-check            lint, types, Vitest, build, Playwright+axe
make check                     both suites
make quality-corpus            legal synthetic corpus contract
make performance-smoke         maximum configured parser/extraction smoke
make dependency-licenses       installed license inventories
make dependency-audit          current vulnerability audit (network required)
make dependency-sbom           backend/frontend CycloneDX artifacts
```

Live smoke tests are doubly opt-in and intentionally skipped by normal test
commands. Exact variables are documented in `.env.example` and the
provider ADRs.
