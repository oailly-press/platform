"""Shelf-specific Pass-1 deltas.

The base gates establish that an artifact is a book. Shelf gates establish the extra
artifact contract declared in SHELVES.md. They inspect author data with platform-owned
code; author-supplied evaluation programs are never executed here.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from common import (FICTION_NOVEL_FLOOR, FICTION_NOVELLA_RANGE, finding,
                    read_chapter, split_code_fences, word_count)


FMR_SHELF = "for-machine-readers"
FMR_SERIES = "o'ailly for machine readers"
FMR_MIN_CASES = 10
FMR_MIN_FAMILIES = 3
FICTION_SHELF = "fiction"
FICTION_AUDIT_VERSION = "1.0"
FICTION_FORMS = {"novel", "novella"}
FICTION_THREAD_STATES = {"resolved", "intentional-ambiguity"}


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


def _fiction_words(manifest: dict, book_dir: Path) -> int:
    total = 0
    for chapter in manifest.get("structure", {}).get("chapters", []):
        text = read_chapter(book_dir, chapter.get("source_file", ""))
        if text is None:
            continue
        prose, _ = split_code_fences(text)
        total += word_count(prose)
    return total


def _valid_chapter(value, chapter_numbers: set[int]) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value in chapter_numbers


def _check_fiction(manifest: dict, book_dir: Path) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    book = manifest.get("book", {})
    form = book.get("fiction_form")
    measured_words = _fiction_words(manifest, book_dir)
    chapters = manifest.get("structure", {}).get("chapters", [])
    chapter_numbers = {
        chapter.get("number") for chapter in chapters
        if isinstance(chapter.get("number"), int)
    }
    metrics: dict = {
        "shelf": FICTION_SHELF,
        "form": form,
        "measured_words": measured_words,
        "continuity_audit": "missing",
    }

    if form not in FICTION_FORMS:
        findings.append(finding(
            "shelf", "reject", "FICTION_FORM_INVALID",
            "FICTION requires book.fiction_form to be 'novel' or 'novella'",
            "book.fiction_form",
        ))
    elif form == "novel" and measured_words < FICTION_NOVEL_FLOOR:
        findings.append(finding(
            "shelf", "reject", "FICTION_NOVEL_TOO_SHORT",
            f"fiction_form 'novel' requires at least {FICTION_NOVEL_FLOOR} measured "
            f"body words; found {measured_words}",
            "book",
        ))
    elif form == "novella" and not (
        FICTION_NOVELLA_RANGE[0] <= measured_words <= FICTION_NOVELLA_RANGE[1]
    ):
        findings.append(finding(
            "shelf", "reject", "FICTION_NOVELLA_LENGTH_MISMATCH",
            f"fiction_form 'novella' requires {FICTION_NOVELLA_RANGE[0]}–"
            f"{FICTION_NOVELLA_RANGE[1]} measured body words; found {measured_words}",
            "book",
        ))

    path = book_dir / "fiction-audit.json"
    if not path.is_file():
        findings.append(finding(
            "shelf", "reject", "FICTION_AUDIT_MISSING",
            "FICTION requires fiction-audit.json with narrator access rules, character "
            "ranges, timeline coverage, world rules, and resolved or intentionally "
            "ambiguous threads",
            "fiction-audit.json",
        ))
        return findings, metrics

    audit = _load_json(path, "FICTION_AUDIT_INVALID", findings)
    if not isinstance(audit, dict):
        return findings, metrics
    metrics["continuity_audit"] = "loaded"

    if audit.get("version") != FICTION_AUDIT_VERSION:
        findings.append(finding(
            "shelf", "reject", "FICTION_AUDIT_VERSION_INVALID",
            f"fiction-audit.json version must be {FICTION_AUDIT_VERSION!r}",
            "fiction-audit.json",
        ))
    if form in FICTION_FORMS and audit.get("form") != form:
        findings.append(finding(
            "shelf", "reject", "FICTION_AUDIT_FORM_MISMATCH",
            "fiction-audit.json form must match book.fiction_form",
            "fiction-audit.json",
        ))

    narrator = audit.get("narrator")
    if not isinstance(narrator, dict):
        findings.append(finding(
            "shelf", "reject", "FICTION_NARRATOR_AUDIT_MISSING",
            "fiction-audit.json requires a narrator object",
            "fiction-audit.json",
        ))
    else:
        if not isinstance(narrator.get("mode"), str) or not narrator["mode"].strip():
            findings.append(finding(
                "shelf", "reject", "FICTION_NARRATOR_MODE_MISSING",
                "narrator.mode must be a non-empty string",
                "fiction-audit.json",
            ))
        access = narrator.get("access_rules")
        if not isinstance(access, list) or len(access) < 2 or not all(
            isinstance(rule, str) and rule.strip() for rule in access
        ):
            findings.append(finding(
                "shelf", "reject", "FICTION_ACCESS_RULES_THIN",
                "narrator.access_rules requires at least two non-empty rules",
                "fiction-audit.json",
            ))
        if not isinstance(narrator.get("uncertainty_policy"), str) or not narrator[
            "uncertainty_policy"
        ].strip():
            findings.append(finding(
                "shelf", "reject", "FICTION_UNCERTAINTY_POLICY_MISSING",
                "narrator.uncertainty_policy must state how unknowns are narrated",
                "fiction-audit.json",
            ))

    characters = audit.get("characters")
    character_ids: set[str] = set()
    if not isinstance(characters, list) or len(characters) < 3:
        findings.append(finding(
            "shelf", "reject", "FICTION_CHARACTERS_THIN",
            "continuity audit requires at least three character records",
            "fiction-audit.json",
        ))
        characters = []
    for index, character in enumerate(characters):
        loc = f"fiction-audit.json.characters[{index}]"
        if not isinstance(character, dict):
            findings.append(finding("shelf", "reject", "FICTION_CHARACTER_INVALID",
                                    "character record must be an object", loc))
            continue
        required = {"id", "name", "role", "first_chapter", "last_chapter"}
        missing = required - set(character)
        if missing:
            findings.append(finding(
                "shelf", "reject", "FICTION_CHARACTER_FIELD_MISSING",
                f"character record missing fields {sorted(missing)}", loc,
            ))
            continue
        character_id = character.get("id")
        if not isinstance(character_id, str) or not character_id.strip():
            findings.append(finding("shelf", "reject", "FICTION_CHARACTER_ID_INVALID",
                                    "character id must be a non-empty string", loc))
        elif character_id in character_ids:
            findings.append(finding("shelf", "reject", "FICTION_CHARACTER_ID_DUPLICATE",
                                    f"duplicate character id {character_id!r}", loc))
        else:
            character_ids.add(character_id)
        if not all(isinstance(character.get(key), str) and character[key].strip()
                   for key in ("name", "role")):
            findings.append(finding(
                "shelf", "reject", "FICTION_CHARACTER_TEXT_INVALID",
                "character name and role must be non-empty strings", loc,
            ))
        first, last = character.get("first_chapter"), character.get("last_chapter")
        if not _valid_chapter(first, chapter_numbers) or not _valid_chapter(last, chapter_numbers):
            findings.append(finding(
                "shelf", "reject", "FICTION_CHARACTER_RANGE_INVALID",
                "first_chapter and last_chapter must reference manifest chapters", loc,
            ))
        elif first > last:
            findings.append(finding(
                "shelf", "reject", "FICTION_CHARACTER_RANGE_REVERSED",
                "first_chapter cannot follow last_chapter", loc,
            ))

    timeline = audit.get("timeline")
    event_ids: set[str] = set()
    covered: set[int] = set()
    prior_sequence = None
    dependencies: list[tuple[str, list[str], str]] = []
    if not isinstance(timeline, list) or not timeline:
        findings.append(finding(
            "shelf", "reject", "FICTION_TIMELINE_MISSING",
            "continuity audit requires timeline events", "fiction-audit.json",
        ))
        timeline = []
    for index, event in enumerate(timeline):
        loc = f"fiction-audit.json.timeline[{index}]"
        if not isinstance(event, dict):
            findings.append(finding("shelf", "reject", "FICTION_TIMELINE_EVENT_INVALID",
                                    "timeline event must be an object", loc))
            continue
        required = {"id", "chapter", "sequence", "description"}
        missing = required - set(event)
        if missing:
            findings.append(finding(
                "shelf", "reject", "FICTION_TIMELINE_FIELD_MISSING",
                f"timeline event missing fields {sorted(missing)}", loc,
            ))
            continue
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            findings.append(finding("shelf", "reject", "FICTION_TIMELINE_ID_INVALID",
                                    "timeline id must be a non-empty string", loc))
        elif event_id in event_ids:
            findings.append(finding("shelf", "reject", "FICTION_TIMELINE_ID_DUPLICATE",
                                    f"duplicate timeline id {event_id!r}", loc))
        else:
            event_ids.add(event_id)
        if not isinstance(event.get("description"), str) or not event["description"].strip():
            findings.append(finding(
                "shelf", "reject", "FICTION_TIMELINE_DESCRIPTION_INVALID",
                "timeline description must be a non-empty string", loc,
            ))
        chapter = event.get("chapter")
        if not _valid_chapter(chapter, chapter_numbers):
            findings.append(finding(
                "shelf", "reject", "FICTION_TIMELINE_CHAPTER_INVALID",
                "timeline chapter must reference a manifest chapter", loc,
            ))
        else:
            covered.add(chapter)
        sequence = event.get("sequence")
        if not isinstance(sequence, (int, float)) or isinstance(sequence, bool):
            findings.append(finding(
                "shelf", "reject", "FICTION_TIMELINE_SEQUENCE_INVALID",
                "timeline sequence must be numeric", loc,
            ))
        elif prior_sequence is not None and sequence <= prior_sequence:
            findings.append(finding(
                "shelf", "reject", "FICTION_TIMELINE_NOT_ORDERED",
                "timeline sequence values must increase in file order", loc,
            ))
        else:
            prior_sequence = sequence
        depends = event.get("depends_on", [])
        if not isinstance(depends, list) or not all(isinstance(item, str) for item in depends):
            findings.append(finding(
                "shelf", "reject", "FICTION_TIMELINE_DEPENDENCY_INVALID",
                "depends_on must be a list of timeline ids", loc,
            ))
        else:
            dependencies.append((event_id, depends, loc))
    missing_chapters = chapter_numbers - covered
    if missing_chapters:
        findings.append(finding(
            "shelf", "reject", "FICTION_TIMELINE_COVERAGE_INCOMPLETE",
            f"timeline lacks events for chapters {sorted(missing_chapters)}",
            "fiction-audit.json",
        ))
    event_order = {
        event.get("id"): index for index, event in enumerate(timeline)
        if isinstance(event, dict) and isinstance(event.get("id"), str)
    }
    for event_id, depends, loc in dependencies:
        unknown = set(depends) - event_ids
        if unknown or event_id in depends:
            findings.append(finding(
                "shelf", "reject", "FICTION_TIMELINE_DEPENDENCY_UNKNOWN",
                f"timeline dependency invalid: unknown={sorted(unknown)}, self={event_id in depends}",
                loc,
            ))
            continue
        later = [dependency for dependency in depends
                 if event_order.get(dependency, -1) >= event_order.get(event_id, -1)]
        if later:
            findings.append(finding(
                "shelf", "reject", "FICTION_TIMELINE_DEPENDENCY_FORWARD",
                f"timeline dependencies must name earlier events; found {sorted(later)}",
                loc,
            ))

    rules = audit.get("world_rules")
    rule_ids: set[str] = set()
    if not isinstance(rules, list) or len(rules) < 3:
        findings.append(finding(
            "shelf", "reject", "FICTION_WORLD_RULES_THIN",
            "continuity audit requires at least three world rules",
            "fiction-audit.json",
        ))
        rules = []
    for index, rule in enumerate(rules):
        loc = f"fiction-audit.json.world_rules[{index}]"
        if not isinstance(rule, dict):
            findings.append(finding("shelf", "reject", "FICTION_WORLD_RULE_INVALID",
                                    "world rule must be an object", loc))
            continue
        required = {"id", "rule", "introduced_chapter", "tested_chapters"}
        missing = required - set(rule)
        if missing:
            findings.append(finding(
                "shelf", "reject", "FICTION_WORLD_RULE_FIELD_MISSING",
                f"world rule missing fields {sorted(missing)}", loc,
            ))
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip() or rule_id in rule_ids:
            findings.append(finding(
                "shelf", "reject", "FICTION_WORLD_RULE_ID_INVALID",
                "world rule id must be non-empty and unique", loc,
            ))
        else:
            rule_ids.add(rule_id)
        if not isinstance(rule.get("rule"), str) or not rule["rule"].strip():
            findings.append(finding(
                "shelf", "reject", "FICTION_WORLD_RULE_TEXT_INVALID",
                "world rule text must be a non-empty string", loc,
            ))
        introduced = rule.get("introduced_chapter")
        tested = rule.get("tested_chapters")
        if not _valid_chapter(introduced, chapter_numbers):
            findings.append(finding(
                "shelf", "reject", "FICTION_WORLD_RULE_CHAPTER_INVALID",
                "introduced_chapter must reference a manifest chapter", loc,
            ))
        if not isinstance(tested, list) or not tested or not all(
            _valid_chapter(chapter, chapter_numbers) for chapter in tested
        ):
            findings.append(finding(
                "shelf", "reject", "FICTION_WORLD_RULE_TESTS_INVALID",
                "tested_chapters must be a non-empty list of manifest chapters", loc,
            ))
        elif _valid_chapter(introduced, chapter_numbers) and any(
            chapter < introduced for chapter in tested
        ):
            findings.append(finding(
                "shelf", "reject", "FICTION_WORLD_RULE_TEST_PRECEDES_INTRODUCTION",
                "tested_chapters cannot precede introduced_chapter", loc,
            ))

    threads = audit.get("threads")
    thread_ids: set[str] = set()
    ambiguity_count = 0
    if not isinstance(threads, list) or not threads:
        findings.append(finding(
            "shelf", "reject", "FICTION_THREADS_MISSING",
            "continuity audit requires tracked story threads",
            "fiction-audit.json",
        ))
        threads = []
    for index, thread in enumerate(threads):
        loc = f"fiction-audit.json.threads[{index}]"
        if not isinstance(thread, dict):
            findings.append(finding("shelf", "reject", "FICTION_THREAD_INVALID",
                                    "thread must be an object", loc))
            continue
        required = {"id", "status", "introduced_chapter", "resolution_chapter", "note"}
        missing = required - set(thread)
        if missing:
            findings.append(finding(
                "shelf", "reject", "FICTION_THREAD_FIELD_MISSING",
                f"thread missing fields {sorted(missing)}", loc,
            ))
            continue
        thread_id = thread.get("id")
        if not isinstance(thread_id, str) or not thread_id.strip() or thread_id in thread_ids:
            findings.append(finding(
                "shelf", "reject", "FICTION_THREAD_ID_INVALID",
                "thread id must be non-empty and unique", loc,
            ))
        else:
            thread_ids.add(thread_id)
        if not isinstance(thread.get("note"), str) or not thread["note"].strip():
            findings.append(finding(
                "shelf", "reject", "FICTION_THREAD_NOTE_INVALID",
                "thread note must explain its resolution or intentional ambiguity", loc,
            ))
        status = thread.get("status")
        if status not in FICTION_THREAD_STATES:
            findings.append(finding(
                "shelf", "reject", "FICTION_THREAD_UNRESOLVED",
                "thread status must be resolved or intentional-ambiguity",
                loc,
            ))
        elif status == "intentional-ambiguity":
            ambiguity_count += 1
        introduced = thread.get("introduced_chapter")
        resolved = thread.get("resolution_chapter")
        if not _valid_chapter(introduced, chapter_numbers) or not _valid_chapter(
            resolved, chapter_numbers
        ):
            findings.append(finding(
                "shelf", "reject", "FICTION_THREAD_RANGE_INVALID",
                "thread chapters must reference manifest chapters", loc,
            ))
        elif introduced > resolved:
            findings.append(finding(
                "shelf", "reject", "FICTION_THREAD_RANGE_REVERSED",
                "resolution_chapter cannot precede introduced_chapter", loc,
            ))

    refrains = audit.get("refrains", [])
    if not isinstance(refrains, list):
        findings.append(finding(
            "shelf", "reject", "FICTION_REFRAINS_INVALID",
            "refrains must be a list", "fiction-audit.json",
        ))
        refrains = []
    for index, refrain in enumerate(refrains):
        loc = f"fiction-audit.json.refrains[{index}]"
        if not isinstance(refrain, dict) or set(("text", "purpose")) - set(refrain):
            findings.append(finding(
                "shelf", "reject", "FICTION_REFRAIN_FIELD_MISSING",
                "each declared refrain requires text and purpose", loc,
            ))
        elif not all(isinstance(refrain.get(key), str) and refrain[key].strip()
                     for key in ("text", "purpose")):
            findings.append(finding(
                "shelf", "reject", "FICTION_REFRAIN_INVALID",
                "refrain text and purpose must be non-empty strings", loc,
            ))

    metrics.update({
        "character_count": len(characters),
        "timeline_events": len(timeline),
        "chapters_covered": len(covered),
        "world_rule_count": len(rules),
        "thread_count": len(threads),
        "intentional_ambiguities": ambiguity_count,
        "declared_refrains": len(refrains),
    })
    if not findings:
        metrics["continuity_audit"] = "PASS"
    return findings, metrics


def check_shelf(manifest: dict, book_dir: Path) -> tuple[list[dict], dict]:
    shelf = _shelf(manifest)
    if shelf == FMR_SHELF:
        return _check_fmr(manifest, book_dir)
    if shelf == FICTION_SHELF:
        return _check_fiction(manifest, book_dir)
    return [], {"shelf": shelf}
