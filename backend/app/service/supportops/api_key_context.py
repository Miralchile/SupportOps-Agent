from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional


_runtime_config: ContextVar[Optional[Dict[str, str]]] = ContextVar(
    "supportops_runtime_api_key_config",
    default=None,
)


ENV_TO_CONFIG_KEY = {
    "DASHSCOPE_API_KEY": "api_key",
    "DASHSCOPE_BASE_URL": "base_url",
    "SUPPORTOPS_MODEL": "model",
    "DASHSCOPE_EMBEDDING_MODEL": "embedding_model",
    "SUPPORTOPS_PROVIDER": "provider",
}


@contextmanager
def use_api_key_config(config: Optional[Dict[str, Any]]) -> Iterator[None]:
    normalized = {key: str(value) for key, value in (config or {}).items() if value is not None}
    token = _runtime_config.set(normalized or None)
    try:
        yield
    finally:
        _runtime_config.reset(token)


def get_runtime_config_value(env_name: str) -> Optional[str]:
    config = _runtime_config.get()
    if not config:
        return None
    key = ENV_TO_CONFIG_KEY.get(env_name)
    if not key:
        return None
    return config.get(key)


def get_runtime_provider() -> Optional[str]:
    config = _runtime_config.get()
    if not config:
        return None
    return (config.get("provider") or "").lower() or None
