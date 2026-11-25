# Risks and unknowns

Ratings combine current likelihood and impact: `critical`, `high`, `medium`, or
`low`. Owners are roles, not named people. A release gate means implementation
may continue only on paths that do not depend on the unresolved item.

## Active risk register

| ID | Risk | Rating | Mitigation / evidence needed | Owner | Gate |
| --- | --- | --- | --- | --- | --- |
| R-01 | TMDB terms appear to prohibit API/content use with an AI-based application | Critical | Do not implement/enable TMDB; obtain explicit written permission or qualified review for the intended deployment | Product/legal | Live TMDB use |
| R-02 | Subtitle copyright may not permit download, LLM transmission, storage, or excerpt display | Critical | Use synthetic/licensed/upload fixtures; obtain SubDL clarification and establish a takedown/retention policy | Product/legal | Provider-backed release |
| R-03 | Deployment/business model is unknown, so provider commercial terms cannot be assessed | High | Decide private vs public and free vs revenue-generating before live integration | Product | External-provider release |
| R-04 | A subtitle may not match the user's cut, release, frame rate, or timing | High | Show release metadata; require preview; support explicit global offset; do not silently auto-select | Product/backend/frontend | UX acceptance |
| R-05 | Global offset cannot correct nonlinear drift | Medium | State limitation; collect evidence before designing frame-rate/drift correction | Product | None for MVP |
| R-06 | LLM output may hallucinate meanings, CEFR, pronunciation, or cue references | High | Strict schema plus local grounding, bounds, dedupe/ranking; golden evaluation; show estimates/limitations | Backend/product | Analyzer acceptance |
| R-07 | Subtitle text can contain prompt-injection-like instructions | High | Implemented fixed instructions, no tools, strict schema, and local grounding; validate with the legal golden set before acceptance | Backend/security | Analyzer acceptance |
| R-08 | Malicious uploads/archives can cause traversal, decompression bombs, resource exhaustion, or XSS | Critical | Implemented stream limits, traversal/link/encryption/member/ratio checks, direct member reads, plain-text normalization, and hostile synthetic tests | Backend/security | Live provider file acceptance |
| R-09 | SubDL v1/v2 coexistence and malformed v2 examples indicate schema/documentation drift | High | v2-only defensive mapping and synthetic contracts are implemented; real scrubbed responses remain required | Backend | SubDL acceptance |
| R-10 | Provider quotas/outages can break the main workflow | High | Quota-aware errors, bounded retries, feature flags, upload fallback, adapter replacement path | Backend/operations | Public release |
| R-11 | LLM cost and latency are unknown for realistic intervals | High | Maximum interval/items/tokens; measure a golden corpus; configurable model; cost metrics and per-client limits | Backend/product | Model selection/public release |
| R-12 | `store=false` does not remove default LLM abuse-monitoring retention | High | Disclose processing; send minimum text; review DPA/region/ZDR needs and subtitle rights | Product/privacy | Public analyzer release |
| R-13 | A shared private login does not establish per-user transcript ownership | High | Private profile uses edge Basic auth, opaque IDs, TTL, and per-client-IP limits; add accounts or abuse-resistant anonymous ownership before multi-user public deployment | Backend/security | Public deployment |
| R-14 | In-memory sessions disappear on restart and cannot support multiple workers | Medium | Accept for controlled MVP; shared encrypted TTL store before horizontal scale | Backend/operations | Scaled deployment |
| R-15 | Persisting or logging subtitle/analyzer text could leak copyrighted or user-supplied data | High | No body logging; transient bytes; bounded in-memory sessions; retention/deletion tests | Backend/operations | All releases |
| R-16 | Quality cannot be judged without a legal evaluation corpus and rubric | High | Create synthetic/licensed golden cues and human scoring rubric before selecting a model | Product/linguistic QA | Model selection |
| R-17 | Pronunciation format/accent and reliable source are unspecified | Medium | Keep optional; product decides accent/notation; do not fabricate missing values | Product | Pronunciation feature |
| R-18 | CEFR for idioms/slang is inherently uncertain and no source is selected | Medium | Label as estimate with confidence; evaluate usefulness; allow null | Product/linguistic QA | CEFR claims |
| R-19 | Search result posters may have separate rights/attribution requirements | Medium | Do not display posters until source and rights are documented | Product/legal | Poster feature |
| R-20 | Public uploads and provider calls invite abuse and unexpected spend | Critical | Auth or abuse-resistant anonymous identity, rate limits, quotas, request limits, budgets, monitoring | Security/operations | Public deployment |
| R-21 | The repository has no declared project license, so redistribution and contribution rights are unspecified | Medium | Product/legal selects a project license and adds the license file and package metadata before distribution | Product/legal | Public distribution |
| R-22 | Process-local metrics and rate limits reset on restart and are not cluster-consistent | Medium | Accept only for the enforced one-worker private profile; use shared telemetry/rate-limit state before scaling | Backend/operations | Scaled deployment |
| R-23 | Automated accessibility scanning cannot prove complete accessibility | Medium | Axe browser checks plus semantic/component coverage are implemented; complete keyboard, screen-reader, zoom, contrast, and cognitive manual audit before public release | Frontend/product | Public deployment |

## Product decisions required

1. Deployment and monetization model.
2. Target jurisdictions, age range, privacy notice, and retention policy.
3. Whether SRT upload is a supported user workflow or development fallback only.
4. Maximum expected scene duration and desired maximum learning items.
5. Default learner level and whether users must choose one.
6. Pronunciation accent/notation, or removal of pronunciation from MVP.
7. Human quality rubric and acceptable error/unsupported-claim threshold.
8. Whether limited subtitle context can be shown and how much.

## Provider questions to resolve

### SubDL

- Is a subtitle-learning application an allowed API use?
- May downloaded subtitle text be transiently sent to a third-party LLM?
- May short cue excerpts be displayed with derived explanations?
- What caching duration, deletion, attribution, and takedown requirements apply?
- Does `format=file` reliably return one file, and what are the documented
  content types/redirect hosts/maximum sizes?
- Is there a stable machine-readable v2 schema or OpenAPI specification?

### TMDB

- Does the AI-application restriction apply when TMDB data is used only for
  title selection and is never placed in an LLM request?
- If the answer can be yes by agreement, which license, attribution, commercial,
  cache-expiry, and purge terms apply to the intended deployment?

### Analyzer provider

- Is processing this subtitle text allowed under provider terms and the
  subtitle source rights?
- Are regional processing, DPA, Modified Abuse Monitoring, or Zero Data
  Retention required?
- Which exact model snapshot passes the project quality/cost/latency gates?

## Technical spikes, in order

These spikes produce evidence and tests, not product features:

1. Parser corpus: validate pysubs2 mapping and normalization on synthetic SRT
   edge cases; decide encoding policy.
2. Analyzer harness: run fake and recorded schema outputs through grounding,
   deduplication, and ranking before any live model call.
3. Licensed golden set: define scoring and baseline candidate model/prompt.
4. SubDL contract probe after permission: capture search/list/download/error
   shapes and verify redirect/content/archive constraints.
5. Timing usability: verify the offset convention and preview workflow with a
   few differently synchronized legal fixtures.

## Review cadence

Revisit this register after every provider terms/API change, before public or
commercial deployment, and whenever a roadmap phase closes. Closed risks remain
in history with the evidence and decision that closed them; they are not simply
deleted.
