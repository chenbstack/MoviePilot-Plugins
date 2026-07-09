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
        self.assertEqual(plugin._bridge_token, "")
        self.assertRegex(plugin._bridge_token_hash, r"^[0-9a-f]{64}$")
        self.assertIsNotNone(plugin.saved_config)
        self.assertEqual(plugin.saved_config["bridge_token"], "")
        self.assertEqual(plugin.saved_config["bridge_token_hash"], plugin._bridge_token_hash)

    def test_get_api_registers_bridge_routes_with_apikey_auth(self):
        module = load_plugin_module()
        plugin = module.MediaAgentBridge()

        routes = plugin.get_api()
        route_by_path = {route["path"]: route for route in routes}

        self.assertEqual(set(route_by_path), {"/ping", "/snapshot", "/export", "/revoke"})
        self.assertEqual(route_by_path["/ping"]["methods"], ["GET"])
        self.assertEqual(route_by_path["/snapshot"]["methods"], ["GET"])
        self.assertEqual(route_by_path["/export"]["methods"], ["GET"])
        self.assertEqual(route_by_path["/revoke"]["methods"], ["POST"])
        self.assertTrue(all(route["auth"] == "apikey" for route in routes))


if __name__ == "__main__":
    unittest.main()
