# Operations and runbooks

## Service objectives and signals

No public SLO is approved yet. For controlled evaluation, watch:

- edge/backend `up` and health probe success;
- request volume, status class, and average HTTP latency;
- analysis count, average analyzer latency, and input/output token totals;
- stable application error codes, especially parse, analyzer, provider quota,
  and resource-limit errors; and
- host/container CPU, memory, restart count, disk, TLS expiry, and egress.

`GET /metrics` uses Prometheus text format and is protected in the private
profile. It deliberately contains no subtitle, expression, movie title,
session ID, client IP, prompt, or model-output label. The sample alert rules and
Grafana dashboard live under `deploy/observability/`; adapt their datasource,
receivers, and thresholds to the selected platform.

Provider remaining-quota gauges cannot be finalized until real approved SubDL
contracts exist. `provider_rate_limited` is the current fail-closed signal.
Analyzer cost is represented by token totals; currency estimates remain an
offline evaluation concern until an exact model and price record are approved.

## Incident triage

1. Establish impact without inspecting or copying user content: health,
   aggregate metrics, container state, deploy version, and correlation IDs.
2. If confidentiality may be affected, disable edge access and provider feature
   flags, preserve content-free system/audit evidence, rotate affected secrets,
   and notify the privacy/security owner.
3. If cost abuse or quota exhaustion occurs, disable the relevant provider,
   retain upload fallback, rotate credentials when compromise is suspected, and
   reconcile provider usage outside application logs.
4. If availability regresses after a release, use the rollback procedure in
   `DEPLOYMENT.md`. A restart deletes all transcript sessions by design.
5. Record timeline, scope, safe error/correlation evidence, root cause,
   remediation, and follow-up tests. Never put subtitle text in the incident
   record unless an approved legal process explicitly requires it.

## Provider degradation

- Capabilities advertise provider/analyzer availability from startup
  configuration; disabled SubDL leaves manual upload available.
- Provider timeout, malformed response, quota, archive, and resource failures
  map to stable actionable errors without exposing provider bodies.
- SubDL retries only transient idempotent reads once; downloads and LLM analysis
  are not blindly replayed.
- On sustained SubDL failure, disable it and show upload-only operation. On
  analyzer failure, keep upload and preview available and avoid pretending the
  fake analyzer is a live educational substitute.

## Deletion and expiry verification

For each staging candidate, create a synthetic session and record only its
opaque ID:

1. `DELETE /api/v1/transcript-sessions/{id}` must return `204`; preview must then
   return `session_not_found`.
2. Create another session, wait beyond the configured TTL, then preview; it must
   return `session_expired` on first lookup and missing thereafter.
3. Create a third session and restart the backend; lookup must fail because
   memory is not durable.
4. Inspect application storage/configuration to ensure no body logs, raw upload,
   archive extraction tree, database, queue, object, or backup was created.

## Takedown/privacy request

The application currently stores no account/history mapping. For a supplied
unexpired opaque session ID, call the delete endpoint or restart the one backend
process to clear all sessions. Disable a disputed provider capability while the
request is reviewed. Preserve only content-free incident metadata needed by the
approved policy. A public launch requires named legal/privacy contacts,
jurisdiction-specific response times, identity verification, and published
policy text; the repository does not fabricate those decisions.

## Maintenance cadence

- Every change: locked lint/type/unit/integration/browser gates.
- Every release candidate: corpus/performance tests, manual accessibility and
  quality review, SBOM/license/vulnerability and container scan, secret/TLS/CORS
  audit, deletion drill, staging smoke, and rollback exercise.
- Regularly and after advisories: dependency/base-image updates through reviewed
  lockfile changes.
- After provider/API/terms/price changes: recheck official documents, contracts,
  adapters, evaluation thresholds, disclosures, and ADR status before enabling.
