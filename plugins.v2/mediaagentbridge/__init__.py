from typing import Any, Dict, List, Tuple

from fastapi import Header, HTTPException, Query

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase

from .exporter import build_export_page, generate_bridge_token, hash_bridge_token, verify_bridge_token


EXPORT_TYPES = (
    "system_settings",
    "plugin_configs",
    "plugin_data",
    "sites",
    "subscriptions",
    "subscribe_history",
    "download_history",
    "download_files",
    "transfer_history",
)


class MediaAgentBridge(_PluginBase):
    plugin_name = "Media Agent 迁移桥"
    plugin_desc = "为 Media Agent 提供 MoviePilot 只读迁移快照和增量同步端点。"
    plugin_icon = "sync.png"
    plugin_version = "0.1.3"
    plugin_author = "chenbstack"
    author_url = "https://github.com/chenbstack"
    plugin_config_prefix = "mediaagentbridge_"
    plugin_order = 5
    auth_level = 1

    _enabled = False
    _bridge_token = ""
    _bridge_token_hash = ""
    _generated_bridge_token = ""
    _include_sensitive_default = False

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        self._bridge_token = str(config.get("bridge_token") or "").strip()
        self._generated_bridge_token = ""
        self._bridge_token_hash = str(config.get("bridge_token_hash") or "")
        self._include_sensitive_default = bool(config.get("include_sensitive_default"))

        reset_bridge_token = bool(config.get("reset_bridge_token"))
        token_to_hash = self._bridge_token
        if self._enabled and (reset_bridge_token or not token_to_hash):
            token_to_hash = generate_bridge_token()
            self._bridge_token = token_to_hash
            self._generated_bridge_token = token_to_hash
        if token_to_hash:
            next_hash = hash_bridge_token(token_to_hash)
            self._bridge_token_hash = next_hash
            if (
                reset_bridge_token
                or str(config.get("bridge_token") or "").strip() != token_to_hash
                or str(config.get("bridge_token_hash") or "") != next_hash
            ):
                updated = dict(config)
                updated["bridge_token"] = token_to_hash
                updated["bridge_token_hash"] = self._bridge_token_hash
                updated["reset_bridge_token"] = False
                self.update_config(updated)
        elif reset_bridge_token:
            updated = dict(config)
            updated["reset_bridge_token"] = False
            self.update_config(updated)

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/ping",
                "endpoint": self.ping,
                "methods": ["GET"],
                "allow_anonymous": True,
                "summary": "Media Agent 迁移桥检测",
                "description": "检测插件状态、协议版本和可导出类型。",
            },
            {
                "path": "/snapshot",
                "endpoint": self.snapshot,
                "methods": ["GET"],
                "allow_anonymous": True,
                "summary": "Media Agent 迁移快照",
                "description": "返回可迁移对象类型和数量。",
            },
            {
                "path": "/export",
                "endpoint": self.export,
                "methods": ["GET"],
                "allow_anonymous": True,
                "summary": "Media Agent 分页导出",
                "description": "按类型分页导出迁移数据，默认脱敏。",
            },
            {
                "path": "/revoke",
                "endpoint": self.revoke,
                "methods": ["POST"],
                "allow_anonymous": True,
                "summary": "吊销 Media Agent 迁移授权",
                "description": "清除桥接 token，后续需重新配置后才能同步。",
            },
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用迁移桥"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "include_sensitive_default",
                                            "label": "默认允许导出敏感字段",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "bridge_token",
                                            "label": "桥接 Token",
                                            "placeholder": "留空自动生成；保存后会显示在设置和详情中",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "reset_bridge_token",
                                            "label": "重新生成桥接 Token",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "bridge_token": self._bridge_token,
            "bridge_token_hash": "",
            "generated_bridge_token": self._generated_bridge_token,
            "reset_bridge_token": False,
            "include_sensitive_default": False,
        }

    def get_page(self) -> List[dict]:
        if not self._bridge_token:
            return []
        return [
            {
                "component": "VAlert",
                "props": {
                    "type": "warning",
                    "variant": "tonal",
                },
                "content": [
                    {
                        "component": "div",
                        "text": "Media Agent 迁移时使用下面的桥接 Token。",
                    },
                    {
                        "component": "code",
                        "text": self._bridge_token,
                    },
                ],
            },
        ]

    def stop_service(self):
        pass

    def ping(self, x_media_agent_bridge_token: str = Header(None, alias="X-Media-Agent-Bridge-Token")) -> Dict[str, Any]:
        self.__authorize(x_media_agent_bridge_token)
        return {
            "success": True,
            "protocol": "media-agent-moviepilot-bridge.v1",
            "plugin": {
                "id": self.__class__.__name__,
                "name": self.plugin_name,
                "version": self.plugin_version,
            },
            "moviepilot": {
                "version_flag": getattr(settings, "VERSION_FLAG", ""),
            },
            "export_types": list(EXPORT_TYPES),
        }

    def snapshot(self, x_media_agent_bridge_token: str = Header(None, alias="X-Media-Agent-Bridge-Token")) -> Dict[str, Any]:
        self.__authorize(x_media_agent_bridge_token)
        types = []
        for source_type in EXPORT_TYPES:
            try:
                count = len(self.__load_rows(source_type))
                error = ""
            except Exception as err:
                logger.error(f"MediaAgentBridge 统计 {source_type} 失败：{err}")
                count = 0
                error = str(err)
            types.append({"type": source_type, "count": count, "error": error})
        return {
            "protocol": "media-agent-moviepilot-bridge.v1",
            "types": types,
        }

    def export(
        self,
        source_type: str = Query("subscriptions", alias="type"),
        cursor: str = Query("", description="上一页返回的 next_cursor"),
        limit: int = Query(200, ge=1, le=1000),
        updated_since: str = Query("", description="仅导出该 UTC 时间之后更新的数据"),
        include_sensitive: bool = Query(False),
        x_media_agent_bridge_token: str = Header(None, alias="X-Media-Agent-Bridge-Token"),
    ) -> Dict[str, Any]:
        self.__authorize(x_media_agent_bridge_token)
        if source_type not in EXPORT_TYPES:
            raise HTTPException(status_code=400, detail=f"不支持的导出类型：{source_type}")
        allowed_sensitive = include_sensitive and self._include_sensitive_default
        return build_export_page(
            source_type,
            self.__load_rows(source_type),
            cursor=cursor,
            limit=limit,
            include_sensitive=allowed_sensitive,
            updated_since=updated_since or None,
        )

    def revoke(self, x_media_agent_bridge_token: str = Header(None, alias="X-Media-Agent-Bridge-Token")) -> Dict[str, Any]:
        self.__authorize(x_media_agent_bridge_token)
        self._bridge_token = ""
        self._bridge_token_hash = ""
        self._generated_bridge_token = ""
        self.update_config({
            "enabled": False,
            "bridge_token": "",
            "bridge_token_hash": "",
            "reset_bridge_token": False,
            "include_sensitive_default": self._include_sensitive_default,
        })
        self._enabled = False
        return {"success": True}

    def __authorize(self, token: str):
        if not self._enabled:
            raise HTTPException(status_code=403, detail="Media Agent 迁移桥未启用")
        if not self._bridge_token_hash:
            raise HTTPException(status_code=403, detail="Media Agent 迁移桥未配置 token")
        if not verify_bridge_token(token or "", self._bridge_token_hash):
            raise HTTPException(status_code=401, detail="Media Agent 迁移桥 token 无效")

    def __load_rows(self, source_type: str) -> List[Any]:
        if source_type == "system_settings":
            return [{"key": key, "value": value} for key, value in (self.systemconfig.all() or {}).items()]
        if source_type == "plugin_configs":
            return [
                {"key": key, "plugin_id": key.removeprefix("plugin."), "value": value}
                for key, value in (self.systemconfig.all() or {}).items()
                if str(key).startswith("plugin.")
            ]
        if source_type == "sites":
            from app.db.site_oper import SiteOper
            return SiteOper().list() or []
        if source_type == "subscriptions":
            from app.db.subscribe_oper import SubscribeOper
            return SubscribeOper().list() or []
        if source_type == "subscribe_history":
            from app.db.models.subscribehistory import SubscribeHistory
            return SubscribeHistory.list() or []
        if source_type == "download_history":
            from app.db.models.downloadhistory import DownloadHistory
            return DownloadHistory.list() or []
        if source_type == "download_files":
            from app.db.models.downloadhistory import DownloadFiles
            return DownloadFiles.list() or []
        if source_type == "transfer_history":
            from app.db.models.transferhistory import TransferHistory
            return TransferHistory.list() or []
        if source_type == "plugin_data":
            from app.db.models.plugindata import PluginData
            return PluginData.list() or []
        raise HTTPException(status_code=400, detail=f"不支持的导出类型：{source_type}")
