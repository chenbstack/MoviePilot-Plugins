import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORTER_PATH = ROOT / "plugins.v2" / "mediaagentbridge" / "exporter.py"


def load_exporter():
    spec = importlib.util.spec_from_file_location("mediaagentbridge_exporter", EXPORTER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MediaAgentBridgeExporterTest(unittest.TestCase):
    def test_to_plain_data_redacts_sensitive_fields_by_default(self):
        exporter = load_exporter()

        class Site:
            id = 12
            name = "Example"
            cookie = "uid=1; pass=secret"
            passkey = "abc123"
            _private = "ignored"

        data = exporter.to_plain_data({
            "site": Site(),
            "headers": {"Authorization": "Bearer secret", "User-Agent": "MoviePilot"},
            "tokens": [{"api_token": "secret-token", "label": "public"}],
        })

        self.assertEqual(data["site"]["cookie"], "[redacted]")
        self.assertEqual(data["site"]["passkey"], "[redacted]")
        self.assertNotIn("_private", data["site"])
        self.assertEqual(data["headers"]["Authorization"], "[redacted]")
        self.assertEqual(data["headers"]["User-Agent"], "MoviePilot")
        self.assertEqual(data["tokens"][0]["api_token"], "[redacted]")
        self.assertEqual(data["tokens"][0]["label"], "public")

    def test_to_plain_data_can_include_sensitive_fields_when_explicitly_allowed(self):
        exporter = load_exporter()

        data = exporter.to_plain_data(
            {"cookie": "uid=1", "password": "secret", "name": "site"},
            include_sensitive=True,
        )

        self.assertEqual(data["cookie"], "uid=1")
        self.assertEqual(data["password"], "secret")
        self.assertEqual(data["name"], "site")

    def test_bridge_token_is_verified_by_hash(self):
        exporter = load_exporter()

        digest = exporter.hash_bridge_token("temporary-token")

        self.assertNotEqual(digest, "temporary-token")
        self.assertTrue(exporter.verify_bridge_token("temporary-token", digest))
        self.assertFalse(exporter.verify_bridge_token("wrong-token", digest))
        self.assertFalse(exporter.verify_bridge_token("", digest))

    def test_build_export_page_returns_stable_hashes_and_cursor(self):
        exporter = load_exporter()
        rows = [
            {"id": 1, "name": "A", "cookie": "secret"},
            {"id": 2, "name": "B", "cookie": "secret"},
        ]

        first = exporter.build_export_page("sites", rows, cursor="", limit=1)
        second = exporter.build_export_page("sites", rows, cursor=first["next_cursor"], limit=1)

        self.assertEqual(first["type"], "sites")
        self.assertEqual(first["total"], 2)
        self.assertEqual(first["done"], False)
        self.assertEqual(first["items"][0]["source_id"], "1")
        self.assertEqual(first["items"][0]["data"]["cookie"], "[redacted]")
        self.assertRegex(first["items"][0]["hash"], r"^[0-9a-f]{64}$")

        self.assertEqual(second["items"][0]["source_id"], "2")
        self.assertEqual(second["done"], True)
        self.assertEqual(second["next_cursor"], "")

        reordered = {"name": "A", "cookie": "secret", "id": 1}
        self.assertEqual(first["items"][0]["hash"], exporter.stable_hash(exporter.to_plain_data(reordered)))

    def test_sensitive_hash_tracks_exported_sensitive_content_when_allowed(self):
        exporter = load_exporter()

        without_sensitive = exporter.build_export_item("sites", {"id": 1, "cookie": "old"}, 1)
        with_sensitive_old = exporter.build_export_item("sites", {"id": 1, "cookie": "old"}, 1, include_sensitive=True)
        with_sensitive_new = exporter.build_export_item("sites", {"id": 1, "cookie": "new"}, 1, include_sensitive=True)

        self.assertNotEqual(without_sensitive["hash"], with_sensitive_old["hash"])
        self.assertNotEqual(with_sensitive_old["hash"], with_sensitive_new["hash"])


if __name__ == "__main__":
    unittest.main()
