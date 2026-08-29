from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PLATFORM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLATFORM / "queue"))
SPEC = importlib.util.spec_from_file_location(
    "oailly_submit_judge_draft", PLATFORM / "queue" / "submit_judge_draft.py"
)
submit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = submit
SPEC.loader.exec_module(submit)


class JudgeDraftSubmissionTests(unittest.TestCase):
    def test_outer_markdown_transport_fence_is_removed_only(self):
        draft = "```markdown\n# Judge verdict\n\n```\nheader\n```\n"
        self.assertEqual(
            submit.normalize_transport_wrapper(draft),
            "# Judge verdict\n\n```\nheader\n",
        )

    def test_unclosed_transport_fence_is_rejected(self):
        with self.assertRaisesRegex(submit.RevisionError, "does not close"):
            submit.normalize_transport_wrapper("```markdown\n# Judge verdict\n")


if __name__ == "__main__":
    unittest.main()
