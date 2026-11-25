# External services and libraries

## Research scope

Reviewed against official documentation on 2026-08-27. Provider policies,
quotas, API schemas, model availability, package compatibility, and prices are
time-sensitive. An implementation session must re-check the linked official
page before adding or upgrading an integration.

This document is technical research, not legal advice.

## Service recommendation summary

| Capability | Candidate | Decision |
| --- | --- | --- |
| Movie search | SubDL v2 movie search | Provisional MVP candidate |
| Subtitle listing/download | SubDL v2 | Provisional; rights/retention gate open |
| Movie search alternative | TMDB v3/v4 | Blocked for this AI application pending clearance |
| Language analysis | Provider-neutral port | Required architecture |
| First LLM adapter | OpenAI Responses API | Provisional after evaluation/privacy gate |
| Development subtitle input | User-supplied licensed/synthetic SRT | Approved path |

## SubDL v2

Official sources:

- [SubDL Developer API](https://subdl.com/at/developers)
- [SubDL Terms of Service](https://subdl.com/terms)
- [Legacy v1 API documentation](https://subdl.com/api-doc)

Current documented behavior:

- Base URL is `https://api.subdl.com`.
- Authentication should use `Authorization: Bearer` or `X-API-Key`. Avoid the
  legacy query-string API key because URLs are more likely to be logged.
- `GET /api/v2/movies/search` searches title/IMDb input, accepts a `movie` type
  and a result limit from 1 to 30, and returns SubDL, IMDb, and TMDB IDs.
- `GET /api/v2/subtitles/search` accepts a SubDL/IMDb/TMDB ID or title/file name;
  `type` is required with TMDB ID because ID plus media type is the identity.
- `GET /api/v2/subtitles/{nId}/download` downloads an archive or attempts a
  single file with `format=file`.
- Responses advertise rate-limit limit, remaining, and reset headers. The
  documented free tier currently allows 2,000 searches and 50 downloads per
  day; Pro lists 30,000 and 2,000 respectively.
- The terms require compliance with API, rate-limit, authentication, and caching
  rules, prohibit limit bypass/resale without permission, and state that the
  downloader is responsible for lawful use of downloaded subtitles.

Critical findings:

- The current v2 and older v1 documentation coexist and describe different
  paths, authentication styles, response shapes, and some different limits.
  New work must target v2 only.
- At review time, the rendered v2 batch filename-search examples contain
  malformed duplicated command text. Do not copy examples blindly; capture and
  validate actual response contracts using a dedicated test key.
- The published terms do not explicitly answer whether downloaded subtitles may
  be sent to an independent LLM, what limited excerpts may be displayed, or how
  long an application may cache files. Those are release gates.
- Search results include `poster_url`, but image origin/license/attribution is
  not sufficiently documented for this project. Do not display posters in MVP.
- The app only needs search, list, and download. Do not use SubDL translation,
  transcription, or AI filename search.

Adapter requirements:

- map v2 payloads defensively and retain unknown-field tolerance;
- use the SubDL `sd_id` as the adapter's primary movie ID;
- filter optional year locally because v2 movie search does not document a year
  parameter;
- request English only and preserve release, hearing-impaired, format, and FPS
  metadata when returned;
- validate every returned download path against the configured SubDL origin;
- surface quota reset information through safe application errors;
- bound downloads while streaming and safely inspect archives; and
- never log keys, download URLs containing credentials, or subtitle text.

## TMDB

Official sources:

- [TMDB API terms](https://www.themoviedb.org/api-terms-of-use)
- [Application authentication](https://developer.themoviedb.org/v4/docs/authentication-application)
- [Movie search](https://developer.themoviedb.org/reference/search-movie)
- [Rate limiting](https://developer.themoviedb.org/docs/rate-limiting)
- [FAQ and attribution](https://developer.themoviedb.org/docs/faq)

Technical behavior if eligibility is later established:

- Application authentication can use the API Read Access Token as a Bearer
  token across v3 and v4.
- Movie search is `GET /3/search/movie`, with title query and optional year.
- TMDB says legacy fixed rate limits are disabled but approximate upper limits
  near 40 requests/second can apply and `429` must be respected.
- Attribution requires an approved TMDB logo and prescribed notice in an About
  or Credits area.
- Published terms limit cache duration to six months and require purging content
  when access terminates.

Blocking issue:

The published API terms say the API or TMDB content must not be used in
connection with an ML/AI-based application, and separately constrain commercial
and chatbot uses. Because this product's central feature is LLM-based language
analysis, the original plan to use TMDB is not assumed permitted even if TMDB
data itself would not be included in the prompt. `ADR-003` therefore blocks the
adapter pending explicit clearance.

## OpenAI API candidate

Official sources:

- [Create a response](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Data controls](https://developers.openai.com/api/docs/guides/your-data)

Relevant current behavior:

- The Responses API accepts text input and JSON-schema structured output.
- Strict structured output improves shape conformance but does not establish
  factual grounding, so local domain validation remains required.
- `store` controls whether a response is stored for later retrieval. The adapter
  must explicitly send `store=false` and avoid conversation/background features
  for the MVP.
- API data is not used to train models unless the customer opts in, according to
  current official documentation.
- Default abuse-monitoring logs may contain prompts/responses and can be retained
  for up to 30 days. Zero Data Retention and Modified Abuse Monitoring require
  approval; `store=false` does not by itself remove abuse-monitoring retention.
- Responses expose status, incomplete/error information, model, usage, and
  output content that the adapter must handle instead of assuming one successful
  text item.

Adapter requirements:

- use the official Python SDK only inside the adapter;
- configure and report the exact model identifier used;
- use a versioned strict schema, `store=false`, no tools, bounded output tokens,
  and explicit timeout;
- treat refusal, incomplete response, timeout, rate limit, invalid structured
  output, and transport failure as distinct cases;
- send only selected cue text and learner settings, with subtitle text clearly
  delimited as untrusted data;
- do not log request/response bodies; capture token counts and latency; and
- re-run the golden evaluation and cost/latency benchmark before changing model
  or prompt/schema version.

No model is selected in this documentation pass. Selection without the project's
quality set would create false precision and become stale quickly.

Phase 6 implementation verification (2026-08-27): the lockfile resolves the
official OpenAI Python SDK 2.54.0. The adapter uses `responses.create`, searches
all output through the SDK's `output_text` helper, requires completed status,
and records usage without bodies. Offline tests exercise request shape,
structured mapping, empty/refused/incomplete/invalid output, timeout,
connection, rate-limit, and status failures. Live use still requires the
separate policy acknowledgement, key, exact model, and opt-in smoke variables.

Phase 7 implementation verification (2026-08-27): SubDL v2 search, list, and
download are implemented behind explicit policy acknowledgement and a server-
side key. Tests use generated/synthetic HTTP responses because permission to
capture and redistribute real responses is not established. The adapter makes
one retry only for transient idempotent reads, validates configured HTTPS
download hosts, streams within bounds, and never exposes download URLs to the
browser. Current terms reviewed were last updated 2026-06-17; the unresolved
questions in `RISKS.md` still block live acceptance.

## Backend libraries

### Python and dependency management

- Target Python 3.12 or newer during scaffolding, after verifying every locked
  dependency on the chosen CI versions.
- Use [uv projects and lockfiles](https://docs.astral.sh/uv/concepts/projects/layout/).
  Commit `pyproject.toml` and `uv.lock`; run CI with the lockfile checked/frozen.
- Exact package versions are selected and locked during scaffolding. This file
  intentionally does not prescribe versions that will become stale.

### FastAPI, Pydantic, and HTTPX

- [FastAPI dependency injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
  supports injecting ports/resources and dependency overrides for tests.
- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/) uses HTTPX
  and pytest. Async tests should follow the framework's documented ASGI
  transport/lifespan behavior.
- Use Pydantic v2 for HTTP/provider DTO validation and
  [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
  for typed environment configuration. Do not use it for domain entities.
- Use strict validation where coercion would obscure contract errors; Pydantic's
  [strict-mode documentation](https://docs.pydantic.dev/latest/concepts/strict_mode/)
  notes that JSON still has some type-specific exceptions, so domain mapping
  must remain explicit.
- Use a lifespan-managed `httpx.AsyncClient`. HTTPX documents separate
  [connect/read/write/pool timeouts](https://www.python-httpx.org/advanced/timeouts/)
  and [connection limits](https://www.python-httpx.org/advanced/resource-limits/).
  Configure both rather than disabling timeouts.

Phase 1 compatibility verification (2026-08-26): the lockfile resolves FastAPI
0.141.1 with Starlette 1.6.0. Current
[Starlette testing documentation](https://www.starlette.io/testclient/) builds
its in-process `TestClient` on `httpx2` and deprecates the legacy HTTPX path, so
`httpx2` is a development-only dependency for ASGI integration tests. HTTPX
remains the selected runtime client for future outbound provider adapters; the
two packages are not allowed to cross into the domain or application layers.

Phase 3 compatibility verification (2026-08-26): FastAPI's current upload
documentation still requires `python-multipart` for form/file parsing and
supports async chunk reads from `UploadFile`; the application pins the new
direct dependency range and the lockfile resolves `python-multipart` 0.0.32.
The application uses FastAPI lifespan for session cleanup and an async service
dependency so request handling does not require a worker thread merely to read
application state.

### Subtitle parsing and archives

- [pysubs2](https://pysubs2.readthedocs.io/en/latest/supported-formats.html) has
  explicit SubRip support and can normalize supported formatting. Wrap it behind
  `SubtitleParser`; do not expose its `SSAFile`/event types to the domain.
- Limit MVP parsing to SRT even though the library supports more formats.
  Broader format support requires fixtures and product acceptance.
- Python's [zipfile documentation](https://docs.python.org/3/library/zipfile.html)
  warns against extracting untrusted archives without inspection. The adapter
  should read an approved member directly and apply stricter path, type, count,
  compressed/uncompressed size, and ratio checks.
- Encoding fallback should use a small explicit policy. Add a detection library
  only if fixtures prove UTF-8/UTF-8-BOM and a documented fallback insufficient.

Phase 2 compatibility verification (2026-08-26): the lockfile resolves pysubs2
1.9.0. Its current API accepts Unicode input through
`SSAFile.from_string(..., format_="srt")`; byte decoding therefore remains an
explicit adapter policy (UTF-8 with BOM handling, then CP-1252) before library
parsing. pysubs2 types do not cross the adapter boundary.

### Backend quality tools

Use pytest, pytest's AnyIO support, Ruff, and mypy. Add an HTTPX-aware mock
transport (for example RESPX) only when adapter contract tests are introduced.
Add dependencies one at a time with a documented purpose; do not install a large
framework extra by default when the application does not use its components.

## Frontend libraries

- Use [React with TypeScript](https://react.dev/learn/typescript).
- Use [Vite](https://vite.dev/guide/) for the development/build tool and enforce
  its current Node requirement in `.nvmrc`/tool configuration and CI. At review
  time Vite documents Node 20.19+ or 22.12+, but implementation must re-check.
- Use [Vitest](https://vitest.dev/guide/) and Testing Library for component and
  workflow behavior. Add browser end-to-end tooling only with the first E2E test.
- Prefer the platform `fetch` API behind one typed client module. Generate types
  from the backend OpenAPI schema only after the API schemas stabilize; avoid a
  second handwritten copy of every response type.

No component library, global state library, router, or server-state library is
required for the first single-page workflow. Add one only when demonstrated UI
complexity warrants it.

Phase 1 compatibility verification (2026-08-26): Node 22.23.2, React 19.2.8,
TypeScript 6.0.3, Vite 8.2.2, and Vitest 4.1.11 install and pass the locked
frontend quality gate. Node and its type definitions are both pinned to the 22.x
line.

## Phase 8–9 deployment and accessibility verification

Rechecked against current official documentation on 2026-08-27:

- [FastAPI container guidance](https://fastapi.tiangolo.com/deployment/docker/)
  recommends building an application image from the official Python base and
  using one process per container where cluster/container replication owns
  scaling. The backend image therefore runs one Uvicorn worker and the current
  memory/rate-limit assumptions forbid replicas.
- [FastAPI HTTPS guidance](https://fastapi.tiangolo.com/deployment/https/) places
  TLS termination at a proxy, and its
  [proxy-forwarding guidance](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)
  warns that forwarded headers must be trusted only from the configured proxy.
  Compose consequently does not publish the backend; only the Caddy edge can
  reach it.
- Docker's [multi-stage build](https://docs.docker.com/build/building/multi-stage/)
  and [production Compose](https://docs.docker.com/compose/how-tos/production/)
  guidance support separating build/runtime contents and layering explicit
  production configuration. Docker Compose
  [secret mounts](https://docs.docker.com/reference/compose-file/services/#secrets)
  expose only granted secrets as read-only `/run/secrets/*` files; settings and
  the edge entrypoint consume those paths.
- Caddy's [Basic authentication](https://caddyserver.com/docs/caddyfile/directives/basic_auth)
  requires a password hash and is safe only over HTTPS. Its
  [automatic HTTPS documentation](https://caddyserver.com/docs/automatic-https)
  covers managed public certificates and local-CA behavior. The edge uses a
  mounted hash, never plaintext configuration, and an HTTPS site address.
- Prometheus documents the
  [text exposition format](https://prometheus.io/docs/instrumenting/exposition_formats/)
  used by the content-free `/metrics` endpoint.
- Playwright's official
  [accessibility-testing guidance](https://playwright.dev/docs/next/accessibility-testing)
  integrates `@axe-core/playwright` and explicitly notes that automated scans
  do not replace manual assessment. The E2E flow scans WCAG A/AA states, while
  manual review remains a release gate.

## Re-verification checklist

Before implementing an external adapter or upgrading it:

1. Open the current official endpoint, authentication, quota, error, and terms
   pages.
2. Record the check date and any changed assumption here.
3. Confirm the adapter feature flag and required secrets.
4. Update sanitized contract fixtures and tests.
5. Re-evaluate privacy, copyright, retention, attribution, and commercial-use
   implications.
6. For an analyzer, run schema tests, golden quality evaluation, latency, and
   cost measurements before accepting the change.
