import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PluginMarketShapeTest(unittest.TestCase):
    def test_v2_market_contains_only_autosub_and_media_agent_bridge(self):
        package_v2 = json.loads((ROOT / "package.v2.json").read_text(encoding="utf-8"))
        package_v1 = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

        self.assertEqual(set(package_v2), {"AutoSubv2", "MediaAgentBridge"})
        self.assertEqual(package_v1, {})
        self.assertTrue((ROOT / "plugins.v2" / "autosubv2" / "__init__.py").exists())
        self.assertTrue((ROOT / "plugins.v2" / "mediaagentbridge" / "__init__.py").exists())
        self.assertFalse((ROOT / "plugins").exists())


if __name__ == "__main__":
    unittest.main()
