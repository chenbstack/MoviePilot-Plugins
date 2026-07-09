import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REDACTED = "[redacted]"
SENSITIVE_KEY_PARTS = (
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "secret",
    "token",
    "cookie",
    "password",
    "passwd",
    "passkey",
    "credential",
)


def is_sensitive_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def to_plain_data(value: Any, include_sensitive: bool = False, _key: str = "") -> Any:
    is_container = isinstance(value, (dict, list, tuple, set)) or hasattr(value, "__dict__") or hasattr(value, "__table__")
    if _key and is_sensitive_key(_key) and not include_sensitive and not is_container:
        return REDACTED
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(k): to_plain_data(v, include_sensitive=include_sensitive, _key=str(k))
            for k, v in value.items()
            if not str(k).startswith("_")
        }
    if isinstance(value, (list, tuple, set)):
        return [to_plain_data(item, include_sensitive=include_sensitive) for item in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return to_plain_data(value.model_dump(), include_sensitive=include_sensitive)
    if hasattr(value, "dict") and callable(value.dict):
        return to_plain_data(value.dict(), include_sensitive=include_sensitive)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return to_plain_data(value.to_dict(), include_sensitive=include_sensitive)
    if hasattr(value, "__table__"):
        columns = getattr(value.__table__, "columns", [])
        return {
            column.name: to_plain_data(getattr(value, column.name, None), include_sensitive=include_sensitive, _key=column.name)
            for column in columns
        }
    if hasattr(value, "__dict__"):
        data = {
            key: to_plain_data(val, include_sensitive=include_sensitive, _key=key)
            for key, val in vars(value).items()
            if not key.startswith("_") and not callable(val)
        }
        for key in dir(value):
            if key.startswith("_") or key in data:
                continue
            try:
                val = getattr(value, key)
            except Exception:
                continue
            if callable(val):
                continue
            data[key] = to_plain_data(val, include_sensitive=include_sensitive, _key=key)
        return data
    return str(value)


def stable_hash(value: Any, include_sensitive: bool = False) -> str:
    payload = json.dumps(
        to_plain_data(value, include_sensitive=include_sensitive),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_bridge_token(token: str) -> str:
    token = token or ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_bridge_token() -> str:
    return secrets.token_urlsafe(32)


def verify_bridge_token(provided: str, configured_hash: str) -> bool:
    if not provided or not configured_hash:
        return False
    return hmac.compare_digest(hash_bridge_token(provided), configured_hash)


def encode_cursor(offset: int) -> str:
    if offset <= 0:
        return ""
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> int:
    if not cursor:
        return 0
    padding = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return 0
    offset = data.get("offset")
    return offset if isinstance(offset, int) and offset > 0 else 0


def source_id_for(data: Dict[str, Any], fallback: int) -> str:
    for key in ("id", "sid", "uuid", "key", "name", "domain", "download_hash", "src", "path"):
        value = data.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return str(fallback)


def exported_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_export_item(source_type: str, row: Any, index: int, include_sensitive: bool = False) -> Dict[str, Any]:
    data = to_plain_data(row, include_sensitive=include_sensitive)
    if not isinstance(data, dict):
        data = {"value": data}
    return {
        "source_type": source_type,
        "source_id": source_id_for(data, index),
        "hash": stable_hash(data, include_sensitive=include_sensitive),
        "data": data,
    }


def build_export_page(
    source_type: str,
    rows: Iterable[Any],
    cursor: str = "",
    limit: int = 200,
    include_sensitive: bool = False,
) -> Dict[str, Any]:
    all_rows: List[Any] = list(rows or [])
    safe_limit = min(max(int(limit or 200), 1), 1000)
    offset = decode_cursor(cursor)
    page_rows = all_rows[offset:offset + safe_limit]
    next_offset = offset + len(page_rows)
    done = next_offset >= len(all_rows)
    return {
        "protocol": "media-agent-moviepilot-bridge.v1",
        "type": source_type,
        "total": len(all_rows),
        "cursor": cursor or "",
        "next_cursor": "" if done else encode_cursor(next_offset),
        "done": done,
        "exported_at": exported_at(),
        "items": [
            build_export_item(source_type, row, offset + idx + 1, include_sensitive=include_sensitive)
            for idx, row in enumerate(page_rows)
        ],
    }
