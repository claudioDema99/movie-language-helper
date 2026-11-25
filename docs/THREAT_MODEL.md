# Threat model

## Scope and security profile

This review covers the React browser application, Caddy edge, one FastAPI
process, its in-memory transcript store, optional SubDL/OpenAI connections, and
the build/deployment files in this repository. The implemented deployment is a
controlled private evaluation profile, not an anonymous public service.

Security invariants:

- subtitle and analyzer text never enters logs, metric labels, URLs, or health
  responses;
- the browser cannot choose an upstream URL or receive a provider credential;
- only bounded SRT input is accepted and provider archives are never extracted;
- the analyzer cannot call tools and its output is untrusted until locally
  grounded;
- parsed transcripts expire from process memory and are not backed up; and
- provider adapters start disabled and credentials alone do not enable them.

## Assets and trust boundaries

| Asset | Boundary | Primary protection |
| --- | --- | --- |
| User-supplied subtitle text | Browser → edge → API → process memory | TLS, authentication, size/parse limits, no-store, TTL, content-free logs |
| Private edge and provider secrets | Compose secret mount → owning process | File-mounted secrets, no browser exposure, redaction, fail-fast validation |
| Provider quota and analyzer budget | API → outbound adapters | Feature/risk gates, bounded requests, zero LLM retries, timeouts, rate limits |
| Learning result integrity | Analyzer → domain | Strict schema, cue/expression grounding, local excerpts/timestamps, dedupe/ranking |
| Service availability | Internet/client → edge/API | Body/archive limits, fixed-window limits, one-worker resource bounds, health checks |
| Copyright/privacy posture | Upload/provider → transient processing | rights acknowledgement, minimum selected text, no durable transcript API/storage |

The edge proxy is trusted to terminate TLS, require Basic authentication,
overwrite/append forwarding headers, and inject the backend bearer token. The
backend must not be published directly. Subtitle files, provider responses,
archive members, analyzer output, all browser input, and supplied request IDs
are untrusted.

## Threats and controls

### Spoofing and ownership

- The edge requires a password hash and never exposes the backend bearer token.
- The backend compares bearer credentials in constant time and accepts product
  routes only through an explicit trusted-host/CORS configuration.
- Session identifiers use cryptographically random URL-safe values.
- Residual risk: one shared private login is not user identity. Anyone with the
  login can use any unexpired session ID they learn. Public multi-user use is
  blocked until sessions have an authenticated owner.

### Tampering and analyzer manipulation

- Pydantic validates HTTP/provider/analyzer boundary structures; domain
  dataclasses recheck business invariants.
- Subtitle prompt-injection text is serialized as delimited data, tools are
  disabled, and returned expressions must occur in cited selected cues.
- Final times and excerpts are reconstructed locally rather than trusted from
  the analyzer.
- Residual risk: a grounded expression can still receive an incorrect meaning;
  the gated human evaluation must measure this before live analyzer acceptance.

### Information disclosure

- No full-transcript endpoint exists; preview/context output is bounded.
- Transcript and analysis responses use `Cache-Control: no-store`; API metrics
  contain bounded route/error labels and aggregate counts only.
- Logs contain method, normalized path metadata, status, duration, correlation
  ID, sizes, and error categories—not bodies, prompts, titles, explanations, or
  secrets.
- Caddy and API add restrictive framing, MIME-sniffing, referrer, permissions,
  and content-security headers.
- Residual risks include browser screenshots/history and provider-side abuse
  monitoring retention; these require user policy disclosure.

### Denial of service and cost abuse

- Requests, uploads, cues, per-cue text, total text, intervals, results,
  timeouts, archive members, expanded bytes, and compression ratios are bounded.
- ZIP paths, links, devices, encryption, nested archives, ambiguous members,
  and unsupported types are rejected before extraction.
- Private requests are limited per edge-reported client address; identities are
  hashed and not used as metric labels.
- The LLM SDK performs no automatic retry, avoiding duplicate ambiguous spend;
  SubDL retries only bounded idempotent reads.
- Residual risk: fixed-window state resets on restart and is not distributed;
  Caddy and the host still need connection/body-rate controls for hostile public
  traffic. Anonymous public deployment remains blocked.

### Elevation, supply chain, and container escape

- The backend runs as an unprivileged user with a read-only filesystem, tmpfs,
  no added capabilities, and `no-new-privileges` in Compose.
- The frontend is a static multi-stage image; the runtime contains neither npm
  dependencies nor source build tooling.
- Lockfiles, automated tests, dependency inventory/license/audit/SBOM commands,
  and container builds form the release evidence.
- Residual risk: base images and third-party packages still require continuous
  vulnerability scanning and digest/SBOM review in the chosen registry.

## Security verification checklist

For each release candidate:

1. Run `make check quality-corpus performance-smoke dependency-audit` and build
   both containers from a clean checkout.
2. Confirm direct backend port 8000 is not published and the edge rejects
   unauthenticated requests.
3. Verify TLS hostname/certificate, strict CORS/hosts, request-size rejection,
   rate-limit `429`, security headers, and content-free logs/metrics.
4. Upload a synthetic subtitle, preview/analyze it, explicitly delete it, then
   prove later lookup fails; repeat after TTL and process restart.
5. Scan the built images and generated SBOMs using the deployment platform's
   approved scanner.
6. Complete the manual accessibility and human language-quality protocols; an
   automated pass is necessary but insufficient.

## Public-release blockers

The following are intentionally not solved by this private profile: legal
privacy/terms text, project license, account/anonymous ownership, global
budget/concurrency enforcement, shared encrypted sessions, distributed rate
limiting/metrics, provider quota contracts, human model-quality acceptance,
formal accessibility sign-off, staging traffic evidence, and named operational
owners. These are release gates, not optional cleanup.
