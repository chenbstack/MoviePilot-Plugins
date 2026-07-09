import importlib
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins.v2"


class FakePluginBase:
    def __init__(self):
        self.saved_config = None
        self.systemconfig = types.SimpleNamespace(all=lambda: {})

    def update_config(self, config, plugin_id=None):
        self.saved_config = config
        return True

    def get_data(self, key=None, plugin_id=None):
        return None

    def save_data(self, key, value, plugin_id=None):
        return True


def install_fake_moviepilot_modules():
    app = types.ModuleType("app")
    plugins = types.ModuleType("app.plugins")
    plugins._PluginBase = FakePluginBase

    core = types.ModuleType("app.core")
    config = types.ModuleType("app.core.config")
    config.settings = types.SimpleNamespace(VERSION_FLAG="v2")

    log = types.ModuleType("app.log")
    log.logger = types.SimpleNamespace(info=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None)

    fastapi = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code, detail):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi.HTTPException = HTTPException
    fastapi.Header = lambda default=None, **kwargs: default
    fastapi.Query = lambda default=None, **kwargs: default

    sys.modules.update({
        "app": app,
        "app.plugins": plugins,
        "app.core": core,
        "app.core.config": config,
        "app.log": log,
        "fastapi": fastapi,
    })


def load_plugin_module():
    install_fake_moviepilot_modules()
    sys.path.insert(0, str(PLUGIN_ROOT))
    sys.modules.pop("mediaagentbridge", None)
    return importlib.import_module("mediaagentbridge")


class MediaAgentBridgePluginTest(unittest.TestCase):
    def test_init_plugin_hashes_plain_bridge_token(self):
        module = load_plugin_module()
        plugin = module.MediaAgentBridge()

        plugin.init_plugin({"enabled": True, "bridge_token": "plain-token"})

        self.assertTrue(plugin.get_state())
        self.assertEqual(plugin._bridge_token, "plain-token")
        self.assertRegex(plugin._bridge_token_hash, r"^[0-9a-f]{64}$")
        self.assertIsNotNone(plugin.saved_config)
        self.assertEqual(plugin.saved_config["bridge_token"], "plain-token")
        self.assertEqual(plugin.saved_config["bridge_token_hash"], plugin._bridge_token_hash)

    def test_init_plugin_auto_generates_and_persists_bridge_token_when_missing(self):
        module = load_plugin_module()
        plugin = module.MediaAgentBridge()

        plugin.init_plugin({"enabled": True})

        self.assertTrue(plugin.get_state())
        self.assertRegex(plugin._bridge_token, r"^[A-Za-z0-9_-]{40,}$")
        self.assertTrue(module.verify_bridge_token(plugin._bridge_token, plugin._bridge_token_hash))
        self.assertEqual(plugin.saved_config["bridge_token"], plugin._bridge_token)
        self.assertEqual(plugin.saved_config["bridge_token_hash"], plugin._bridge_token_hash)
        self.assertFalse(plugin.saved_config["reset_bridge_token"])

    def test_bridge_token_is_shown_on_form_model_and_plugin_page(self):
        module = load_plugin_module()
        plugin = module.MediaAgentBridge()

        plugin.init_plugin({"enabled": True, "bridge_token": "visible-token"})

        _, model = plugin.get_form()

        self.assertEqual(model["bridge_token"], "visible-token")
        self.assertIn("visible-token", str(plugin.get_page()))

    def test_init_plugin_regenerates_bridge_token_when_requested(self):
        module = load_plugin_module()
        plugin = module.MediaAgentBridge()

        plugin.init_plugin({
            "enabled": True,
            "bridge_token": "old-token",
            "bridge_token_hash": module.hash_bridge_token("old-token"),
            "reset_bridge_token": True,
        })

        self.assertTrue(plugin._bridge_token)
        self.assertNotEqual(plugin._bridge_token, "old-token")
        self.assertTrue(module.verify_bridge_token(plugin._bridge_token, plugin._bridge_token_hash))
        self.assertEqual(plugin.saved_config["bridge_token"], plugin._bridge_token)
        self.assertFalse(plugin.saved_config["reset_bridge_token"])

    def test_get_api_registers_bridge_routes_without_moviepilot_auth(self):
        module = load_plugin_module()
        plugin = module.MediaAgentBridge()

        routes = plugin.get_api()
        route_by_path = {route["path"]: route for route in routes}

        self.assertEqual(set(route_by_path), {"/ping", "/snapshot", "/export", "/revoke"})
        self.assertEqual(route_by_path["/ping"]["methods"], ["GET"])
        self.assertEqual(route_by_path["/snapshot"]["methods"], ["GET"])
        self.assertEqual(route_by_path["/export"]["methods"], ["GET"])
        self.assertEqual(route_by_path["/revoke"]["methods"], ["POST"])
        self.assertTrue(all(route["allow_anonymous"] is True for route in routes))
        self.assertTrue(all("auth" not in route for route in routes))


if __name__ == "__main__":
    unittest.main()
