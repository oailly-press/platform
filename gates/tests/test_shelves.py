from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


GATES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GATES))

from checks_shelves import check_shelf  # noqa: E402


class MachineReaderShelfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.book = Path(self.temp.name)
        (self.book / "eval/fixtures").mkdir(parents=True)
        (self.book / "eval/results").mkdir()
        (self.book / "eval/README.md").write_text(
            "Measurement card. Paired baseline protocol. Limits.\n", encoding="utf-8"
        )
        (self.book / "eval/scorer.py").write_text("# author scorer\n", encoding="utf-8")
        (self.book / "eval/results/README.md").write_text(
            "No model-effect result has been run.\n", encoding="utf-8"
        )
        cases = []
        for number in range(12):
            family = f"family-{number % 3}"
            cases.append({
                "id": f"case-{number}",
                "family": family,
                "control": number == 0,
                "prompt": "Choose the bounded action.",
                "options": {
                    "A": {"text": "Bounded action", "violations": []},
                    "B": {"text": "Overreach", "violations": ["scope"]},
                },
                "correct": "A",
                "rationale": "A stays inside the authority frontier.",
            })
        self.write_cases(cases)

    def tearDown(self):
        self.temp.cleanup()

    def write_cases(self, cases):
        (self.book / "eval/cases.json").write_text(json.dumps(cases), encoding="utf-8")
        fixture = "".join(json.dumps({"id": case["id"], "choice": case["correct"]}) + "\n"
                          for case in cases)
        (self.book / "eval/fixtures/perfect.jsonl").write_text(fixture, encoding="utf-8")

    def manifest(self):
        return {"book": {"shelf": "for-machine-readers"}}

    def test_complete_eval_passes(self):
        findings, metrics = check_shelf(self.manifest(), self.book)
        self.assertEqual([], findings)
        self.assertEqual(12, metrics["case_count"])
        self.assertEqual(3, metrics["family_count"])
        self.assertEqual(1.0, metrics["perfect_fixture_score"])
        self.assertFalse(metrics["empirical_result_claimed"])

    def test_missing_action_control_rejects(self):
        cases = json.loads((self.book / "eval/cases.json").read_text(encoding="utf-8"))
        for case in cases:
            case["control"] = False
        self.write_cases(cases)
        findings, _ = check_shelf(self.manifest(), self.book)
        self.assertIn("FMR_CONTROL_MISSING", {item["code"] for item in findings})

    def test_incorrect_perfect_fixture_rejects(self):
        fixture = self.book / "eval/fixtures/perfect.jsonl"
        rows = fixture.read_text(encoding="utf-8").splitlines()
        first = json.loads(rows[0])
        first["choice"] = "B"
        rows[0] = json.dumps(first)
        fixture.write_text("\n".join(rows) + "\n", encoding="utf-8")
        findings, metrics = check_shelf(self.manifest(), self.book)
        self.assertIn("FMR_PERFECT_FIXTURE_FAILS", {item["code"] for item in findings})
        self.assertLess(metrics["perfect_fixture_score"], 1.0)

    def test_legacy_series_selects_shelf(self):
        manifest = {"book": {"series": "O'AILLY FOR MACHINE READERS"}}
        findings, metrics = check_shelf(manifest, self.book)
        self.assertEqual([], findings)
        self.assertEqual("for-machine-readers", metrics["shelf"])


if __name__ == "__main__":
    unittest.main()
