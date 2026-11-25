"""Validate the project-authored golden corpus without calling an analyzer."""

import json
from pathlib import Path
from typing import TypedDict, cast


class CueRecord(TypedDict):
    id: str
    text: str
    context_only: bool


class ExpectedRecord(TypedDict):
    expression: str
    type: str


class CaseRecord(TypedDict):
    id: str
    learner_cefr: str
    cues: list[CueRecord]
    expected: list[ExpectedRecord]
    distractors: list[str]


def main() -> None:
    path = Path(__file__).parents[1] / "evaluation" / "golden.synthetic.json"
    payload = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    assert payload.get("schema_version") == "golden-v1"
    cases = cast(list[CaseRecord], payload.get("cases"))
    assert cases and {case["learner_cefr"] for case in cases} == {
        "A1",
        "A2",
        "B1",
        "B2",
        "C1",
        "C2",
    }
    ids: set[str] = set()
    for case in cases:
        assert case["id"] not in ids
        ids.add(case["id"])
        primary_text = " ".join(
            cue["text"] for cue in case["cues"] if not cue["context_only"]
        ).casefold()
        assert case["expected"] and all(
            expected["expression"].casefold() in primary_text
            for expected in case["expected"]
        )
        all_text = " ".join(cue["text"] for cue in case["cues"]).casefold()
        assert all(
            distractor.strip() and distractor.casefold() in all_text
            for distractor in case["distractors"]
        )
    print(
        f"validated {len(cases)} synthetic golden cases ({payload['schema_version']})"
    )


if __name__ == "__main__":
    main()
