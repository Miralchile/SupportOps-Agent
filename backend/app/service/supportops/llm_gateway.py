"""Observable JSON LLM gateway with explicit fallback semantics."""

from __future__ import annotations

import contextvars
import json
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterator, List, Mapping

from openai import OpenAI

from service.supportops.api_key_context import get_runtime_config_value


_observations: contextvars.ContextVar[List[Dict[str, Any]] | None] = contextvars.ContextVar(
    "supportops_llm_observations", default=None
)


@dataclass
class LLMResult:
    parsed: Dict[str, Any]
    content: str
    provider: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    status: str
    error_type: str | None
    fallback_used: bool
    fallback_reason: str | None
    prompt_version: str
    estimated_cost_usd: float | None = None

    def observation(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("parsed", None)
        data.pop("content", None)
        return data


def _runtime_value(name: str, default: str = "") -> str:
    value = get_runtime_config_value(name)
    if value is None:
        import os

        value = os.getenv(name, default)
    return str(value or default).strip().strip('"').strip("'")


def _valid_key(value: str) -> bool:
    lowered = value.lower()
    return bool(value) and lowered not in {
        "your_api_key", "your-dashscope-api-key", "your_dashscope_api_key", "sk-your-real-dashscope-api-key"
    } and not lowered.startswith("your_")


def _classify_error(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    status = getattr(exc, "status_code", None)
    if status == 429 or "ratelimit" in name:
        return "rate_limit"
    if status is not None and int(status) >= 500:
        return "provider_error"
    if "timeout" in name:
        return "timeout"
    if "connection" in name:
        return "network_error"
    if status in {401, 403} or "authentication" in name or "permission" in name:
        return "authentication_error"
    return "unknown_error"


def _estimated_cost(input_tokens: int, output_tokens: int) -> float | None:
    try:
        input_rate = float(_runtime_value("SUPPORTOPS_INPUT_USD_PER_MILLION_TOKENS", "0"))
        output_rate = float(_runtime_value("SUPPORTOPS_OUTPUT_USD_PER_MILLION_TOKENS", "0"))
    except ValueError:
        return None
    if input_rate <= 0 and output_rate <= 0:
        return None
    return round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 8)


def _schema_error(value: Dict[str, Any], schema: Mapping[str, Any] | None) -> str | None:
    if not schema:
        return None
    missing = [key for key in schema.get("required", []) if key not in value]
    if missing:
        return f"missing required fields: {', '.join(missing)}"
    type_checks = {
        "string": lambda item: isinstance(item, str),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    for key, property_schema in dict(schema.get("properties") or {}).items():
        if key not in value or not isinstance(property_schema, Mapping):
            continue
        expected = property_schema.get("type")
        check = type_checks.get(str(expected))
        if check and not check(value[key]):
            return f"field {key} must be {expected}"
        allowed = property_schema.get("enum")
        if allowed is not None and value[key] not in allowed:
            return f"field {key} is outside enum"
    return None


def _record(result: LLMResult) -> None:
    observations = _observations.get()
    if observations is not None:
        observations.append(result.observation())


@contextmanager
def capture_llm_observations() -> Iterator[List[Dict[str, Any]]]:
    observations: List[Dict[str, Any]] = []
    token = _observations.set(observations)
    try:
        yield observations
    finally:
        _observations.reset(token)


class LLMGateway:
    def generate_json(
        self,
        prompt: str,
        fallback: Mapping[str, Any],
        *,
        prompt_version: str = "unversioned",
        timeout_seconds: float = 30,
        schema: Mapping[str, Any] | None = None,
    ) -> LLMResult:
        started = time.perf_counter()
        api_key = _runtime_value("DASHSCOPE_API_KEY")
        provider = "dashscope"
        model = _runtime_value("SUPPORTOPS_MODEL", "qwen-plus")

        def fallback_result(reason: str, error_type: str | None = None, content: str = "") -> LLMResult:
            result = LLMResult(
                parsed=dict(fallback),
                content=content,
                provider=provider,
                model=model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                input_tokens=0,
                output_tokens=0,
                status="fallback",
                error_type=error_type,
                fallback_used=True,
                fallback_reason=reason,
                prompt_version=prompt_version,
            )
            _record(result)
            return result

        if not _valid_key(api_key):
            return fallback_result("missing_or_placeholder_api_key", "configuration_error")

        try:
            client = OpenAI(
                api_key=api_key,
                base_url=_runtime_value("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            )
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                stream=False,
                timeout=timeout_seconds,
            )
            content = completion.choices[0].message.content if completion.choices else ""
            try:
                parsed = json.loads(content or "")
            except json.JSONDecodeError:
                return fallback_result("invalid_json", "json_decode_error", content or "")
            if not isinstance(parsed, dict):
                return fallback_result("schema_root_not_object", "schema_error", content or "")
            validation_error = _schema_error(parsed, schema)
            if validation_error:
                return fallback_result(f"schema_validation_failed: {validation_error}", "schema_error", content or "")
            usage = getattr(completion, "usage", None)
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            result = LLMResult(
                parsed=parsed,
                content=content or "",
                provider=provider,
                model=model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                status="success",
                error_type=None,
                fallback_used=False,
                fallback_reason=None,
                prompt_version=prompt_version,
                estimated_cost_usd=_estimated_cost(input_tokens, output_tokens),
            )
            _record(result)
            return result
        except Exception as exc:
            error_type = _classify_error(exc)
            return fallback_result(error_type, error_type)


gateway = LLMGateway()
