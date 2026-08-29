from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


PLATFORM = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("oailly_aibn", PLATFORM / "aibn.py")
aibn = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(aibn)


class AibnRegistryLocatorTests(unittest.TestCase):
    def test_live_sibling_checkout_finds_public_registry(self):
        self.assertEqual(
            aibn.REGISTRY,
            PLATFORM.parent / "site-repo" / "aibn" / "registry.json",
        )

    def test_nested_and_standalone_checkouts_are_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            nested_platform = root / "site" / ".platform"
            nested_registry = root / "site" / "aibn" / "registry.json"
            nested_platform.mkdir(parents=True)
            nested_registry.parent.mkdir(parents=True)
            nested_registry.write_text("{}", encoding="utf-8")
            self.assertEqual(aibn.locate_registry(nested_platform), nested_registry)

            standalone_platform = root / "workspace" / "platform"
            standalone_registry = (
                root / "workspace" / "gh" / "site-repo" / "aibn" / "registry.json"
            )
            standalone_platform.mkdir(parents=True)
            standalone_registry.parent.mkdir(parents=True)
            standalone_registry.write_text("{}", encoding="utf-8")
            self.assertEqual(aibn.locate_registry(standalone_platform), standalone_registry)


if __name__ == "__main__":
    unittest.main()
