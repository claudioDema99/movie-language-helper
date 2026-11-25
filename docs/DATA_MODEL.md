# Data model

## Modeling rules

- Domain models are provider-neutral and framework-neutral.
- Time is represented as non-negative integer milliseconds. Floating-point
  seconds are never used in domain calculations.
- External IDs are scoped by provider and media type; a bare integer or string
  is not a movie identity.
- Raw provider responses, HTTP DTOs, and LLM response models do not cross into
  the domain without explicit mapping and validation.
- Optional means genuinely unknown or unavailable. Required fields must not be
  filled with placeholder text.
- Domain values should be immutable once validated.

## Value objects

### `ExternalId`

| Field | Type | Rule |
| --- | --- | --- |
| `provider` | non-empty string | Stable adapter namespace such as `subdl` |
| `media_type` | enum | `movie` in the MVP |
| `value` | non-empty string | Opaque; never parsed by domain code |

Uniqueness is the tuple `(provider, media_type, value)`. TMDB IDs in particular
are not treated as globally unique without media type.

### `Timestamp`

| Field | Type | Rule |
| --- | --- | --- |
| `milliseconds` | integer | `>= 0` |

Conversion to and from `HH:MM:SS,mmm` belongs to the subtitle adapter/parser.

### `TimeRange`

| Field | Type | Rule |
| --- | --- | --- |
| `start` | `Timestamp` | Inclusive |
| `end` | `Timestamp` | Exclusive and greater than `start` |

Two ranges overlap when `left.start < right.end` and
`right.start < left.end`. The half-open convention makes cues ending exactly at
the requested start, or starting exactly at the requested end, non-overlapping.

### `SyncOffset`

A signed integer number of milliseconds. It transforms source subtitle times
to playback/display times:

```text
display_start = cue.start + sync_offset_ms
display_end   = cue.end   + sync_offset_ms
```

Adjusted values below zero are clamped only for display; interval overlap must
be implemented with a tested policy and not unsigned arithmetic.

## Movie and subtitle acquisition

### `MovieMatch`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `key` | `ExternalId` | yes | Primary identity for the chosen adapter |
| `title` | string | yes | Non-blank display title |
| `original_title` | string | no | If supplied by catalog |
| `release_year` | integer | no | Plausible four-digit year |
| `alternate_ids` | tuple of `ExternalId` | no | Provenance retained per ID |
| `subtitle_count` | integer | no | Provider hint, not a guarantee |
| `poster` | URL/reference | no | Disabled until image rights are cleared |

Search results are not persisted as canonical local movie records in the MVP.
The selected `MovieMatch` is copied into the transcript session for display and
traceability.

### `SubtitleCandidate`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `key` | `ExternalId` | yes | Opaque provider subtitle identity |
| `movie_key` | `ExternalId` | yes | Movie identity used for lookup |
| `language` | BCP-47-like internal code | yes | `en` in MVP |
| `release_name` | string | no | Helps user match their movie release |
| `format` | enum/string | no | Only SRT accepted in MVP |
| `hearing_impaired` | boolean | no | Unknown is distinct from false |
| `fps` | decimal | no | Informational; not used for auto-drift repair |
| `provider_rank` | decimal | no | Provider hint, never trusted as domain score |
| `files` | tuple of metadata | no | Archive members when provider exposes them |

No provider download URL is exposed as a public client-controlled field. The
adapter derives or validates its own upstream path from `key`.

### `SubtitlePayload`

An application-boundary value containing bytes or a bounded byte stream plus
trusted acquisition metadata: source, declared format, content type, filename,
and size when known. It is not persisted after parsing.

## Transcript

### `SubtitleCue`

| Field | Type | Rule |
| --- | --- | --- |
| `id` | stable session-local string | Unique within transcript |
| `source_index` | positive integer or null | Original SRT index when valid |
| `range` | `TimeRange` | Positive duration |
| `source_text` | string | Bounded normalized plain text, non-blank |
| `analysis_text` | string | Deterministically normalized, possibly blank if non-dialogue |
| `flags` | set of enum | Examples: `non_dialogue`, `hearing_impaired`, `markup_removed` |

Cue timestamps need not be disjoint; real subtitles can overlap. Parser output
is sorted by `(start, end, source order)`. Duplicate source indices are reported
as warnings rather than used as identity.

`source_text` is sanitized presentation text, not the original byte-for-byte SRT
markup. The raw input digest supplies traceability without retaining raw bytes.

### `Transcript`

| Field | Type | Rule |
| --- | --- | --- |
| `cues` | non-empty tuple of `SubtitleCue` | Bounded count and total text |
| `language` | string | `en` for MVP |
| `content_digest` | SHA-256 hex string | Computed from input bytes or canonical cues |
| `source` | upload/provider metadata | Contains IDs, not API payloads or secrets |
| `warnings` | tuple of typed warnings | Encoding, malformed cue, dropped markup, etc. |

Transcript duration is derived from the greatest cue end. Empty or wholly
invalid subtitles fail parsing; they do not create a session.

### `TranscriptSession`

| Field | Type | Rule |
| --- | --- | --- |
| `id` | cryptographically random opaque ID | Not sequential |
| `transcript` | `Transcript` | Validated |
| `movie` | `MovieMatch` or null | Null for unassociated upload |
| `created_at` | aware UTC datetime | Clock-injected |
| `expires_at` | aware UTC datetime | Later than creation |

The MVP store is process memory with TTL and bounded capacity. Expired sessions
return a distinct `session_expired` error when this can be determined. A session
ID is a capability identifier but is not authentication; public multi-user
deployment requires ownership enforcement.

## Analysis

### `LearnerProfile`

| Field | Type | Rule |
| --- | --- | --- |
| `cefr_level` | enum | `A1`-`C2` or `unspecified` |
| `preferred_item_limit` | integer | Within configured API bounds |
| `pronunciation_preference` | enum/null | Deferred until product choice |

### `AnalysisRequest`

| Field | Type | Rule |
| --- | --- | --- |
| `transcript_session_id` | opaque string | Must resolve and be unexpired |
| `playback_range` | `TimeRange` | Duration within configured maximum |
| `sync_offset` | `SyncOffset` | Within configured absolute bound |
| `learner` | `LearnerProfile` | Validated |
| `item_limit` | integer | Positive and bounded |

An analysis fingerprint is derived from the transcript digest, playback range,
offset, learner settings, analyzer/prompt/schema versions, and ranking version.
It enables reproducibility and future caching without treating provider IDs as
content identity.

### `AnalysisCue`

The analyzer receives an explicit cue ID, adjusted display range, text, and a
boolean indicating whether the cue is inside the requested interval or only
context. It does not receive raw files, download URLs, secrets, or unnecessary
movie metadata.

### `AnalyzerCandidate`

The provider-neutral candidate returned through `LanguageAnalyzer` contains:

- expression and normalized form;
- item type;
- general and contextual meaning;
- optional pronunciation and notation;
- optional CEFR estimate and confidence;
- cue IDs for occurrences;
- optional register/usage note; and
- analyzer salience/confidence signals.

It is intermediate untrusted data. It is not an API learning item until domain
validation succeeds.

### `Occurrence`

| Field | Type | Rule |
| --- | --- | --- |
| `cue_id` | string | Must exist in the analyzed cue set |
| `display_range` | `TimeRange` | Derived from cue and offset, not LLM text |
| `context_excerpt` | string | Derived locally and length-bounded |

The expression must occur in the referenced cue after a documented
case/Unicode/whitespace normalization. The analyzer cannot author timestamps or
context excerpts.

### `LearningItem`

| Field | Type | Rule |
| --- | --- | --- |
| `id` | deterministic result-local string | Stable for identical validated input |
| `expression` | string | Verified against at least one cue |
| `normalized_form` | string | Non-blank |
| `type` | enum | Product vocabulary from `PRODUCT.md` |
| `general_meaning` | string | Non-blank and length-bounded |
| `contextual_meaning` | string | Non-blank and length-bounded |
| `pronunciation` | structured optional value | Includes notation when present |
| `estimated_cefr` | enum/null | Estimate only |
| `confidence` | decimal/null | Clamped to `[0, 1]` |
| `occurrences` | non-empty tuple | Validated locally |
| `relevance_score` | decimal | Domain-computed and clamped to `[0, 1]` |
| `usage_note` | string/null | Length-bounded |

Deduplication uses normalized form plus contextual sense/type, not expression
text alone. The exact algorithm is versioned because it affects user-visible
results.

### `AnalysisResult`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | opaque/deterministic identifier | Does not expose content digest directly |
| `request` | immutable analysis parameters | Excludes session internals |
| `items` | ordered tuple | May be empty with a clear message |
| `warnings` | tuple | Low confidence, truncated context, etc. |
| `provenance` | `AnalysisProvenance` | Reproducibility and diagnostics |
| `created_at` | UTC datetime | Clock-injected |

`AnalysisProvenance` contains analyzer/provider name, model identifier, prompt
version, output-schema version, ranking version, token counts when available,
and latency. It never contains prompts, subtitle text, API keys, or raw provider
responses.

## Error model

Domain/application errors use stable codes grouped as:

- validation: invalid query, range, offset, language, or file;
- transcript: unsupported format, unsafe archive, ambiguous archive, parse
  failure, empty interval, session missing, session expired;
- catalog/subtitle provider: unauthorized, quota limited, unavailable, bad
  response, no results;
- analyzer: unavailable, rate limited, refused, incomplete, invalid output,
  context too large; and
- internal: invariant violation or unexpected failure.

Adapters retain the original exception only as an internal cause. HTTP mapping
and safe user messages belong to the inbound adapter.

## Persistence boundary

No durable relational data model is required for the MVP. Do not introduce a
database schema for hypothetical accounts or history. If durable history is
approved later, store user ownership, request parameters, derived learning
items, and provenance separately from raw transcript text. Any raw-text
retention requires an explicit rights, privacy, encryption, TTL, and deletion
decision first.
