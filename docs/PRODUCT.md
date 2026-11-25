# Product

## Purpose

Movie Language Helper prepares English learners to watch a selected part of an
English-language movie without subtitles. It finds language that is likely to
interrupt comprehension and explains it before the user watches that part.

The product is a preparation tool, not a movie player, subtitle viewer, or
general-purpose dictionary.

## Target user

The initial user is an adult English learner who:

- can identify the movie and the playback interval they plan to watch;
- has an approximate CEFR level, or accepts the default level;
- wants a short, prioritized study list rather than every unfamiliar word; and
- legally has access to the movie and, when uploading a subtitle, the right to
  use that file.

## Core workflow

1. The user searches for a movie by title and optionally narrows by year.
2. The user selects an unambiguous movie result.
3. The user either selects an available English subtitle candidate or uploads
   an English SRT file.
4. The application parses and validates the subtitle and creates a short-lived
   transcript session.
5. The user checks a small preview near a known playback time and can apply a
   global synchronization offset.
6. The user chooses a playback interval and learner level.
7. The application extracts only cues overlapping that interval and analyzes
   them.
8. The application returns a ranked, bounded list of useful learning items with
   timestamps and short contextual excerpts.

Subtitle-provider retrieval remains a product requirement, but it is gated by
the provider and copyright decisions in `DECISIONS.md` and `RISKS.md`. Uploading
an SRT is the development and fallback path; it does not replace provider
retrieval as a product capability.

## MVP scope

The MVP target supports:

- movies only (not TV series or episodes);
- English SRT subtitles;
- title search through one configured movie-catalog adapter;
- provider subtitle selection when the adapter is enabled;
- user-supplied SRT files;
- intervals from 1 second through 10 minutes;
- one global subtitle synchronization offset per transcript session;
- learner levels A1 through C2, plus an `unspecified` value;
- words, idioms, phrasal verbs, slang, and other fixed expressions;
- a synchronous analysis request with a configured upstream timeout; and
- transient processing without accounts, saved libraries, or study history.

The provider-independent evaluation slice may use an unassociated upload and a
fake catalog while provider gates remain open. This is an implementation stage,
not a change to the target search workflow.

The 10-minute maximum is an initial safety, latency, and cost bound. It is a
configuration value whose default must be tested before it changes.

## Learning item

An MVP learning item contains:

- the expression exactly as it appears in the selected cues;
- a normalized form;
- a type: `word`, `idiom`, `phrasal_verb`, `slang`, or `other_expression`;
- a concise general meaning;
- the meaning in this movie context;
- reserved nullable pronunciation/notation fields; the MVP deliberately leaves
  them absent under ADR-013;
- an optional estimated CEFR level and confidence, clearly labeled as an
  estimate;
- one or more occurrence timestamps;
- a short original-context excerpt;
- a user-relative relevance score; and
- optional usage or register notes.

The result must distinguish unavailable information from an empty value. It
must not invent pronunciation, CEFR, or contextual meaning merely to fill a
field.

## Ranking intent

Ranking should favor items that are both useful for understanding the selected
scene and plausibly difficult for the selected learner. It should avoid:

- obvious proper names;
- duplicates and trivial inflection variants;
- items far below the learner's level;
- exhaustive lists of ordinary words; and
- confident claims unsupported by the supplied context.

The language analyzer proposes candidates. Deterministic domain rules validate,
deduplicate, and order them so that provider output cannot directly define
product behavior.

## User-visible limitations

- Third-party subtitles may not match the user's exact release or timing.
- The synchronization offset corrects a constant timing shift, not progressive
  drift caused by different frame rates or edits.
- Language explanations and CEFR estimates can be wrong and are educational
  aids, not authoritative linguistic references.
- Provider availability and quotas may prevent search or download.
- A movie can have no usable English subtitle.

These limitations must be represented in the interface with actionable errors,
not hidden by silently choosing a different movie, subtitle, or interval.

## Out of scope for the MVP

- hosting, streaming, downloading, or identifying a video file;
- displaying or exporting a complete third-party transcript;
- subtitle translation or speech-to-text transcription;
- TV episodes;
- user accounts, payments, saved history, or spaced repetition;
- automatic correction of nonlinear subtitle drift;
- training or fine-tuning a model on movie metadata or subtitles;
- a guarantee that every difficult expression is found;
- pronunciation output until an accent, notation, authoritative source, rights,
  and validation threshold are approved under a new ADR; and
- medical, legal, or other high-stakes interpretation of dialogue.

## Acceptance criteria for the first vertical slice

The vertical slice is complete when a developer can use a licensed test SRT to:

1. create a transcript session;
2. preview cues at a playback timestamp with a documented offset convention;
3. request analysis for a valid interval;
4. receive schema-valid, ranked learning items whose cue references and quoted
   expressions are verified against the selected text; and
5. receive stable domain errors for invalid files, invalid ranges, expired
   sessions, and analyzer failures.

Provider-backed use is a separate milestone that depends on the providers'
legal and licensing terms (see `EXTERNAL_SERVICES.md`).

## Product questions still open

- Is the intended deployment private/non-commercial, public free, or commercial?
- Which jurisdictions and age groups will the first release serve?
- May downloaded subtitles be transmitted to an external LLM for this use?
- Is SRT upload acceptable as a user-facing fallback or only a development aid?
- What quality threshold and evaluation set define an acceptable learning list?
- What approved source, accent, and notation would justify reintroducing the
  pronunciation capability deferred by ADR-013?

These questions are intentionally unresolved and must not be answered by an
implementation session without product-owner input.
