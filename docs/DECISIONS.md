# Architectural decisions

This is the decision log for choices that affect more than one implementation
step. Statuses are `accepted`, `provisional`, `superseded`, or `blocked`.

## ADR-001: Hexagonal backend with strict dependency direction

- Status: accepted
- Date: 2026-08-26

Use domain, application, ports, and adapters. Domain code is pure typed Python
and cannot import web frameworks, SDKs, or provider models.

Reason: movie catalogs, subtitle services, and LLMs are volatile and have
different terms, schemas, and failure modes. Testing domain behavior without a
network is a core project requirement.

Consequence: mapping code is explicit and some similarly shaped models exist at
different boundaries. This duplication is intentional.

## ADR-002: Provider-scoped identity instead of a TMDB-centric domain

- Status: accepted
- Date: 2026-08-26

Represent identity as `(provider, media_type, value)` with alternate external
IDs. No domain type is named `TmdbMovie` or assumes a numeric canonical ID.

Reason: the original design made one vendor's identifier canonical and made
replacement harder. Current TMDB terms also create a material eligibility risk
for an AI-based application.

Consequence: adapters and URLs must carry a provider namespace. Cross-provider
matching is explicit and may be uncertain.

## ADR-003: Do not implement or enable TMDB without written eligibility review

- Status: blocked
- Date: 2026-08-26

The planned TMDB adapter is not part of the initial implementation. Reconsider
only after the intended deployment model is known and TMDB confirms or qualified
legal review establishes that this application is permitted. If enabled later,
implement current authentication, attribution, cache expiry, purge, and
commercial-license requirements.

Reason: TMDB's published API terms prohibit using the API/content in connection
with an AI-based application and impose additional commercial and caching
conditions. The product is explicitly AI-based.

Consequence: SubDL's catalog endpoint is the technical candidate for MVP movie
search. The user-upload flow permits core development without any live catalog.

## ADR-004: SubDL v2 is a candidate adapter, not a trusted domain dependency

- Status: provisional
- Date: 2026-08-26

If provider use is cleared, implement SubDL v2 for movie search, English
subtitle listing, and provider-controlled downloads. Keep `MovieCatalog`,
`SubtitleCatalog`, and `SubtitleSource` as separate ports even if one adapter
implements all three.

Reason: the current official v2 API supports all three capabilities and returns
SubDL, IMDb, and TMDB identifiers, avoiding a required TMDB call. However, SubDL
v1 documentation still coexists, parts of the v2 examples are malformed, and
the terms put responsibility for subtitle rights on the downloader.

Exit criteria for `accepted`:

1. Confirm in writing that application download, transient parsing, limited
   contextual display, and transmission of selected text to the chosen analyzer
   are allowed.
2. Confirm caching/retention rules and required attribution.
3. Capture real scrubbed v2 schemas with a dedicated development API key.
4. Pass adapter contract tests for search, list, download, quota, and errors.

Implementation note (2026-08-27): the v2 adapter, three port capabilities,
archive defenses, capability-gated HTTP/frontend flow, and offline synthetic
contracts exist. This does not change the provisional status: no real schema
capture or live call was permitted, and exit criteria 1–3 remain open.

## ADR-005: SRT upload is the legal and development fallback

- Status: accepted
- Date: 2026-08-26

Support a user-supplied English SRT path before live subtitle download. Require
the user to attest that they may use the file; do not treat that attestation as
a substitute for policy/legal review.

Reason: it enables the complete domain and analysis vertical slice using
synthetic or licensed fixtures, independent of catalog/provider availability.

Consequence: upload security and file-size limits are required in the first API
slice, while provider search can remain feature-flagged.

## ADR-006: Transient bounded transcript sessions; no full transcript API

- Status: accepted
- Date: 2026-08-26

Parse a subtitle into a short-lived session, expose only bounded previews and
learning-item excerpts, and delete on expiry or explicit request. Do not expose
full transcript retrieval/export endpoints.

Reason: this minimizes copyrighted-text exposure and avoids repeatedly parsing
uploads during timing checks and analysis.

Consequence: the local MVP is single-process with an in-memory TTL store. Public
or horizontally scaled deployment needs an ownership-aware shared store and an
explicit retention decision.

## ADR-007: Synchronous analysis first; no in-process background job fiction

- Status: accepted
- Date: 2026-08-26

The MVP `POST /analyses` waits for a bounded analyzer call. Do not return `202`
unless a durable job record and worker exist.

Reason: an interval is small and a synchronous implementation is the smallest
coherent slice. Framework background tasks can be lost on restart and are not a
durable queue.

Consequence: the client needs a visible analyzing state and timeout/retry UX.
Measured latency, not speculation, determines whether an async-job phase is
added.

## ADR-008: LLM output is untrusted candidate data

- Status: accepted
- Date: 2026-08-26

`LanguageAnalyzer` returns candidates, not final learning items. The adapter
requests strict structured output. The domain verifies schema, cue references,
quoted expressions, lengths, enums, confidence ranges, duplicates, and ranking.
Subtitle text is explicitly untrusted and cannot cause tool calls.

Reason: schema conformance alone does not ensure grounding or product quality,
and subtitle text can contain instruction-like content.

Consequence: invalid results fail explicitly or use one separately measured,
bounded repair attempt. Prompts, schemas, and ranking rules are versioned and
evaluated.

## ADR-009: OpenAI Responses API is the first analyzer candidate

- Status: provisional
- Date: 2026-08-26

Build an OpenAI adapter only after the provider-independent fake analyzer and
quality harness exist. Use the official SDK and Responses API with strict
structured output, `store=false`, no tools, explicit timeout/token limits, and a
configured model identifier. Do not hard-code an unversioned model alias in the
domain.

Reason: the official API supports JSON-schema output and stateless requests, but
model quality, price, availability, and retention requirements can change.

Exit criteria for `accepted`: choose a model snapshot using the project golden
set; document cost/latency; review data processing and subtitle-transmission
rights; and confirm deployment-region/privacy requirements.

Implementation note (2026-08-27): the official Responses SDK adapter, strict
versioned schema, `store=false`/no-tools request contract, safe failure mapping,
usage metrics, and offline harness exist. No model alias or snapshot is selected
and no live request was made, so this ADR remains provisional.

## ADR-010: Minimal persistence until durable product needs exist

- Status: accepted
- Date: 2026-08-26

Do not add PostgreSQL, Redis, a queue, or object storage to the first local
vertical slice. Define the transcript-session store as a port and use bounded
memory. Add infrastructure only when provider caching rights, horizontal scale,
accounts, or durable analysis jobs require it.

Reason: the product currently has no account/history requirement, and premature
persistence increases privacy, copyright, deletion, and operational scope.

Consequence: the first deployment is intentionally not horizontally scalable or
durable across restarts.

## ADR-011: Selected implementation stack

- Status: accepted
- Date: 2026-08-26

Use Python 3.12+ with `uv`, FastAPI, Pydantic v2 plus pydantic-settings, HTTPX,
pysubs2, pytest, Ruff, and mypy for the backend. Use React, TypeScript, Vite,
Vitest, and Testing Library for the frontend. Commit lockfiles and verify exact
compatible versions during scaffolding rather than copying versions from this
research date.

Reason: this stack supports typed boundaries, OpenAPI, dependency injection,
async I/O, reproducible environments, and isolated tests without imposing a
full-stack framework.

Consequence: Pydantic belongs only at I/O/configuration boundaries. The frontend
is separately built and deployed. Vite's then-current Node requirement must be
enforced in the scaffold and CI.

## ADR-012: Global offset only in MVP

- Status: accepted
- Date: 2026-08-26

Use `display_time = subtitle_time + sync_offset_ms`. Do not silently attempt
frame-rate conversion or nonlinear drift correction.

Reason: title/year alone cannot identify the user's exact movie release.
Explicit preview and offset make this mismatch visible and testable.

Consequence: release selection and timing warnings are part of the product flow.
More advanced synchronization requires media/release information and a new
decision.

## ADR-013: Pronunciation is explicitly deferred

- Status: accepted
- Date: 2026-08-27

Do not request, synthesize, rank, or promise pronunciation in the release
candidate. The provider-neutral models retain nullable pronunciation fields so
a future reviewed adapter contract does not require a breaking API change, but
the frontend renders them only when present.

Reason: no target accent, notation (IPA versus respelling), authoritative
source, or quality threshold has been chosen. An LLM-only pronunciation value
would present uncertain output as reference data.

Consequence: Phase 8 treats pronunciation as deliberately out of scope. Adding
it requires a new ADR naming the accent, notation, source rights, validation,
and learner-facing label.

## ADR-014: Controlled private deployment is the only implemented server profile

- Status: accepted
- Date: 2026-08-27

Package one backend process with the in-memory TTL store behind a Caddy TLS
edge. The edge requires Basic authentication and injects a separate bearer
credential on backend requests. The backend applies a strict host/CORS
allowlist, request limits, security headers, and a process-local per-edge-client
fixed-window limit. Provider adapters remain fail-closed.

Reason: this profile is reproducible and materially safer for one owner or a
small controlled evaluation without inventing accounts, durable ownership, or
distributed state before the product and privacy decisions exist.

Consequence: this is not an anonymous public-production architecture. Run one
backend worker only. Horizontal scale requires a shared encrypted TTL store and
distributed rate limiter; public access requires an approved identity/ownership
model, budget controls, policies, legal notices, and Phase 9 staging evidence.
