from __future__ import annotations

from threading import Lock

import yaml

from zenith.config.schema import ZenithSettings
from zenith.paths import CONFIG_PATH, ensure_data_dir

_lock = Lock()
_cache: ZenithSettings | None = None


def load_settings() -> ZenithSettings:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        ensure_data_dir()
        if CONFIG_PATH.exists():
            raw = yaml.safe_load(CONFIG_PATH.read_text()) or {}
            _cache = ZenithSettings.model_validate(raw)
        else:
            _cache = ZenithSettings()
            _write(_cache)
        return _cache


def save_settings(settings: ZenithSettings) -> ZenithSettings:
    global _cache
    if settings.location.timezone_auto:
        settings = settings.model_copy(
            update={
                "location": settings.location.model_copy(
                    update={"timezone": settings.location.resolved_timezone()}
                )
            }
        )
    with _lock:
        _cache = settings
        _write(settings)
        return _cache


def replace_settings(data: dict) -> ZenithSettings:
    settings = ZenithSettings.model_validate(data)
    return save_settings(settings)


def update_cache(settings: ZenithSettings) -> ZenithSettings:
    global _cache
    with _lock:
        _cache = settings
        return _cache


def merge_settings(patch: dict) -> ZenithSettings:
    current = load_settings().model_dump(mode="json")
    return update_cache(ZenithSettings.model_validate(_merge(current, patch)))


def persist_cache() -> ZenithSettings:
    return save_settings(load_settings())


def discard_cache() -> ZenithSettings:
    global _cache
    with _lock:
        _cache = None
    return load_settings()


def _merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _write(settings: ZenithSettings) -> None:
    ensure_data_dir()
    payload = settings.model_dump(mode="json")
    CONFIG_PATH.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
