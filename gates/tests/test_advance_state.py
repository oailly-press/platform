from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


PLATFORM = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "oailly_advance_state", PLATFORM / "queue" / "advance_state.py"
)
advance = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = advance
SPEC.loader.exec_module(advance)


class AdvanceStateTests(unittest.TestCase):
    book = "author--state-fixture"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.subs = self.root / "submissions-repo" / "status"
        self.site = self.root / "site-repo" / "status"
        self.subs.mkdir(parents=True)
        self.site.mkdir(parents=True)
        self.paths = tuple(directory / f"{self.book}.json" for directory in (self.subs, self.site))
        status = {
            "book_id": self.book,
            "version_under_review": "v1",
            "state": "2-revision",
            "action_required": "revise",
            "history": [{"date": "2026-08-27", "from": "1-critics", "to": "2-revision"}],
        }
        for path in self.paths:
            path.write_text(json.dumps(status) + "\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, **overrides):
        arguments = {
            "book": self.book,
            "target": "3-verification",
            "mirrors": (self.subs, self.site),
            "version": "v2",
            "reviews_in": 0,
            "today": date(2026, 8, 28),
        }
        arguments.update(overrides)
        return advance.advance_state(**arguments)

    def test_dry_run_is_default_and_changes_neither_mirror(self):
        before = [path.read_text(encoding="utf-8") for path in self.paths]
        result = self.call()
        self.assertEqual(result["result"], "dry-run")
        self.assertEqual(before, [path.read_text(encoding="utf-8") for path in self.paths])

    def test_apply_updates_both_mirrors_with_one_adjacent_transition(self):
        result = self.call(apply=True)
        self.assertEqual(result["result"], "applied")
        statuses = [json.loads(path.read_text(encoding="utf-8")) for path in self.paths]
        self.assertEqual(statuses[0], statuses[1])
        self.assertEqual(statuses[0]["state"], "3-verification")
        self.assertEqual(statuses[0]["version_under_review"], "v2")
        self.assertIsNone(statuses[0]["action_required"])
        self.assertEqual(statuses[0]["history"][-1]["from"], "2-revision")
        self.assertEqual(statuses[0]["history"][-1]["to"], "3-verification")

    def test_non_adjacent_or_published_transition_is_rejected(self):
        with self.assertRaisesRegex(advance.StateError, "non-adjacent"):
            self.call(target="4-judge")
        with self.assertRaisesRegex(advance.StateError, "pre-publication"):
            self.call(target="5-published")

    def test_path_like_book_id_is_rejected(self):
        with self.assertRaisesRegex(advance.StateError, "invalid book-id"):
            self.call(book="../../status")

    def test_divergent_mirrors_fail_before_either_is_written(self):
        divergent = json.loads(self.paths[1].read_text(encoding="utf-8"))
        divergent["state"] = "1-critics"
        self.paths[1].write_text(json.dumps(divergent) + "\n", encoding="utf-8")
        before = [path.read_text(encoding="utf-8") for path in self.paths]
        with self.assertRaisesRegex(advance.StateError, "mirrors disagree"):
            self.call(apply=True)
        self.assertEqual(before, [path.read_text(encoding="utf-8") for path in self.paths])

    def test_revision_state_restores_author_action(self):
        for path in self.paths:
            status = json.loads(path.read_text(encoding="utf-8"))
            status["state"] = "1-critics"
            status["action_required"] = None
            path.write_text(json.dumps(status) + "\n", encoding="utf-8")
        self.call(target="2-revision", version="v1", reviews_in=3, apply=True)
        status = json.loads(self.paths[0].read_text(encoding="utf-8"))
        self.assertEqual(status["action_required"], "revise")

    def test_locator_supports_canonical_and_mirror_checkouts(self):
        canonical_platform = self.root / "canonical" / "platform"
        canonical_platform.mkdir(parents=True)
        canonical_subs = self.root / "canonical" / "gh" / "submissions-repo" / "status"
        canonical_site = self.root / "canonical" / "gh" / "site-repo" / "status"
        canonical_subs.mkdir(parents=True)
        canonical_site.mkdir(parents=True)
        self.assertEqual(
            advance.find_mirrors(canonical_platform), (canonical_subs, canonical_site)
        )


if __name__ == "__main__":
    unittest.main()
