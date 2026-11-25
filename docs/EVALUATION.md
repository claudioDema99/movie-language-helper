# Analyzer evaluation contract

## Status

The offline harness is implemented. The corpus, reviewer calibration, numeric
thresholds, model snapshot, measured latency, and measured price are not yet
approved. Until they are recorded here, the OpenAI adapter must remain disabled
and Phase 6 cannot pass its acceptance gate.

## Rights-cleared case format

Every golden case must record an opaque case ID, provenance/license, learner
level, short synthetic/public-domain/licensed cues, context-only markers,
reviewer-authored acceptable expressions, acceptable variants, and known
distractors. Do not add a movie subtitle merely because it is publicly
downloadable. Corpus content must never be written to logs or test reports.

## Automated metrics

`evaluation.harness.evaluate` reports candidate precision, expected-item
recall, useful-at-N case rate, duplicate rate, unsupported cue-reference rate,
average latency, input/output tokens, and estimated cost when reviewed prices
are supplied. Empty corpora fail rather than producing a misleading pass.

## Human review rubric

Two reviewers should independently score each proposed item from 0–2 on:

- expression grounding and occurrence selection;
- correctness of general and contextual meaning;
- usefulness for the stated learner level;
- concision and clarity;
- register/usage claims; and
- optional CEFR/pronunciation claims when present.

A score of 0 on grounding or meaning is an unsupported-claim failure. Resolve
reviewer disagreements and report agreement. Record thresholds before looking
at candidate-model results; do not tune a threshold merely to accept one run.

## Change control

Changing model, instructions, output schema, grounding, or ranking versions
requires the same frozen corpus, automated report, human review sample, latency,
token, and contemporaneous price comparison. The selected exact model and
results belong in `DECISIONS.md`; secrets and response bodies do not.
