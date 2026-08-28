"""Shelf-specific Pass-1 deltas.

The base gates establish that an artifact is a book. Shelf gates establish the extra
artifact contract declared in SHELVES.md. They inspect author data with platform-owned
code; author-supplied evaluation programs are never executed here.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from common import finding


FMR_SHELF = "for-machine-readers"
FMR_SERIES = "o'ailly for machine readers"
FMR_MIN_CASES = 10
FMR_MIN_FAMILIES = 3


def _shelf(manifest: dict) -> str | None:
    book = manifest.get("book", {})
    explicit = book.get("shelf")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    series = book.get("series")
    if isinstance(series, str) and series.strip().lower() == FMR_SERIES:
        return FMR_SHELF
    return None


def _load_json(path: Path, code: str, findings: list[dict]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        findings.append(finding("shelf", "reject", code,
                                f"cannot read valid JSON: {error}", str(path)))
        return None


def _load_jsonl(path: Path, code: str, findings: list[dict]) -> list[dict] | None:
    try:
        rows = []
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError(f"line {number} is not an object")
            rows.append(value)
        return rows
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        findings.append(finding("shelf", "reject", code,
                                f"cannot read valid JSONL: {error}", str(path)))
        return None


def _require_files(book_dir: Path, relative: list[str], findings: list[dict]) -> bool:
    complete = True
    for name in relative:
        path = book_dir / name
        if not path.is_file():
            findings.append(finding("shelf", "reject", "FMR_EVAL_FILE_MISSING",
                                    f"FOR MACHINE READERS requires {name}", name))
            complete = False
    return complete


def _check_fmr(_manifest: dict, book_dir: Path) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    metrics: dict = {"shelf": FMR_SHELF}
    required = [
        "eval/README.md",
        "eval/cases.json",
        "eval/scorer.py",
        "eval/fixtures/perfect.jsonl",
        "eval/results/README.md",
    ]
    if not _require_files(book_dir, required, findings):
        return findings, metrics

    readme = (book_dir / "eval/README.md").read_text(encoding="utf-8").lower()
    for token, code, description in [
        ("measurement card", "FMR_MEASUREMENT_CARD_MISSING", "a measurement card"),
        ("paired", "FMR_PAIRED_PROTOCOL_MISSING", "a paired before/after protocol"),
        ("baseline", "FMR_BASELINE_MISSING", "a baseline condition"),
        ("limits", "FMR_LIMITS_MISSING", "explicit evaluation limits"),
    ]:
        if token not in readme:
            findings.append(finding("shelf", "reject", code,
                                    f"eval/README.md must declare {description}",
                                    "eval/README.md"))

    cases = _load_json(book_dir / "eval/cases.json", "FMR_CASES_INVALID", findings)
    if cases is None:
        return findings, metrics
    if not isinstance(cases, list):
        findings.append(finding("shelf", "reject", "FMR_CASES_NOT_ARRAY",
                                "eval/cases.json must be a JSON array", "eval/cases.json"))
        return findings, metrics

    metrics["case_count"] = len(cases)
    if len(cases) < FMR_MIN_CASES:
        findings.append(finding("shelf", "reject", "FMR_CASES_TOO_FEW",
                                f"machine-reader eval requires at least {FMR_MIN_CASES} "
                                f"cases; found {len(cases)}", "eval/cases.json"))

    ids: set[str] = set()
    families: Counter[str] = Counter()
    controls = 0
    valid_cases: dict[str, dict] = {}
    required_case = {"id", "family", "control", "prompt", "options", "correct", "rationale"}
    for index, case in enumerate(cases, 1):
        loc = f"eval/cases.json[{index - 1}]"
        if not isinstance(case, dict):
            findings.append(finding("shelf", "reject", "FMR_CASE_INVALID",
                                    "case must be an object", loc))
            continue
        missing = required_case - set(case)
        if missing:
            findings.append(finding("shelf", "reject", "FMR_CASE_FIELD_MISSING",
                                    f"case missing fields {sorted(missing)}", loc))
            continue
        case_id = case.get("id")
        family = case.get("family")
        options = case.get("options")
        if not isinstance(case_id, str) or not case_id:
            findings.append(finding("shelf", "reject", "FMR_CASE_ID_INVALID",
                                    "case id must be a non-empty string", loc))
            continue
        if case_id in ids:
            findings.append(finding("shelf", "reject", "FMR_CASE_ID_DUPLICATE",
                                    f"duplicate case id {case_id!r}", loc))
            continue
        ids.add(case_id)
        if not isinstance(family, str) or not family:
            findings.append(finding("shelf", "reject", "FMR_FAMILY_INVALID",
                                    "family must be a non-empty string", loc))
        else:
            families[family] += 1
        if not isinstance(case.get("control"), bool):
            findings.append(finding("shelf", "reject", "FMR_CONTROL_INVALID",
                                    "control must be boolean", loc))
        elif case["control"]:
            controls += 1
        if not isinstance(options, dict) or len(options) < 2:
            findings.append(finding("shelf", "reject", "FMR_OPTIONS_INVALID",
                                    "options must contain at least two choices", loc))
            continue
        if case.get("correct") not in options:
            findings.append(finding("shelf", "reject", "FMR_ANSWER_INVALID",
                                    "correct must name one option", loc))
            continue
        option_valid = True
        for label, option in options.items():
            if not isinstance(label, str) or not isinstance(option, dict):
                option_valid = False
                break
            if not isinstance(option.get("text"), str) or not isinstance(option.get("violations"), list):
                option_valid = False
                break
        if not option_valid:
            findings.append(finding("shelf", "reject", "FMR_OPTION_SCHEMA_INVALID",
                                    "each option requires string text and list violations", loc))
            continue
        valid_cases[case_id] = case

    metrics["family_count"] = len(families)
    metrics["families"] = dict(sorted(families.items()))
    metrics["action_required_controls"] = controls
    if len(families) < FMR_MIN_FAMILIES:
        findings.append(finding("shelf", "reject", "FMR_FAMILIES_TOO_FEW",
                                f"eval requires at least {FMR_MIN_FAMILIES} behavior "
                                f"families; found {len(families)}", "eval/cases.json"))
    if controls < 1:
        findings.append(finding("shelf", "reject", "FMR_CONTROL_MISSING",
                                "eval needs an action-required/answerable control so "
                                "blanket abstention cannot maximize the metric",
                                "eval/cases.json"))

    perfect = _load_jsonl(book_dir / "eval/fixtures/perfect.jsonl",
                          "FMR_PERFECT_FIXTURE_INVALID", findings)
    if perfect is not None:
        responses: dict[str, str] = {}
        fixture_valid = True
        for index, row in enumerate(perfect, 1):
            if set(row) != {"id", "choice"}:
                findings.append(finding("shelf", "reject", "FMR_FIXTURE_ROW_INVALID",
                                        "fixture rows must contain only id and choice",
                                        f"eval/fixtures/perfect.jsonl:{index}"))
                fixture_valid = False
                continue
            case_id, choice = row["id"], row["choice"]
            if not isinstance(case_id, str) or not isinstance(choice, str):
                findings.append(finding("shelf", "reject", "FMR_FIXTURE_ROW_INVALID",
                                        "fixture id and choice must be strings",
                                        f"eval/fixtures/perfect.jsonl:{index}"))
                fixture_valid = False
                continue
            if case_id in responses:
                findings.append(finding("shelf", "reject", "FMR_FIXTURE_DUPLICATE",
                                        f"duplicate response for {case_id!r}",
                                        f"eval/fixtures/perfect.jsonl:{index}"))
                fixture_valid = False
            responses[case_id] = choice
        if fixture_valid:
            missing = set(valid_cases) - set(responses)
            unknown = set(responses) - set(valid_cases)
            wrong = [case_id for case_id, case in valid_cases.items()
                     if responses.get(case_id) != case["correct"]]
            if missing or unknown or wrong:
                findings.append(finding("shelf", "reject", "FMR_PERFECT_FIXTURE_FAILS",
                                        f"perfect fixture mismatch: {len(missing)} missing, "
                                        f"{len(unknown)} unknown, {len(wrong)} wrong",
                                        "eval/fixtures/perfect.jsonl"))
            metrics["perfect_fixture_score"] = round(
                max(0, len(valid_cases) - len(wrong) - len(missing)) /
                max(1, len(valid_cases)), 4)

    result_readme = (book_dir / "eval/results/README.md").read_text(encoding="utf-8").lower()
    if not any(token in result_readme for token in ("no model-effect result", "model-effect result")):
        findings.append(finding("shelf", "reject", "FMR_RESULT_STATUS_MISSING",
                                "eval/results/README.md must state whether an empirical "
                                "model-effect result exists", "eval/results/README.md"))
    metrics["empirical_result_claimed"] = (
        "no model-effect result" not in result_readme and "model-effect result" in result_readme
    )
    return findings, metrics


def check_shelf(manifest: dict, book_dir: Path) -> tuple[list[dict], dict]:
    shelf = _shelf(manifest)
    if shelf == FMR_SHELF:
        return _check_fmr(manifest, book_dir)
    return [], {"shelf": shelf}
