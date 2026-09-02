"""Typed tool runtime used by the SupportOps planner and workflow.

The registry is deliberately provider-agnostic: a tool can later be backed by
local Python, HTTP, or MCP without changing the planner contract.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Literal, Mapping


ToolHandler = Callable[..., Dict[str, Any]]
ToolStatus = Literal["ok", "not_found", "missing_args", "error", "timeout", "permission_denied"]


class ToolOutputError(ValueError):
    """Raised when a handler violates its declared output contract."""


def _matches_json_type(value: Any, expected: str) -> bool:
    checks = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
        "null": lambda item: item is None,
    }
    check = checks.get(expected)
    return check(value) if check else True


@dataclass(frozen=True)
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None

    def to_json_schema(self) -> Dict[str, Any]:
        schema: Dict[str, Any] = {"type": self.type, "description": self.description}
        if self.default is not None:
            schema["default"] = self.default
        return schema


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    handler: ToolHandler = field(repr=False, compare=False)
    parameters: tuple[ToolParameter, ...] = ()
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    retries: int = 0
    permissions: tuple[str, ...] = ("support:read",)
    side_effect: bool = False
    requires_confirmation: bool = False
    version: str = "1.0.0"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {parameter.name: parameter.to_json_schema() for parameter in self.parameters},
            "required": [parameter.name for parameter in self.parameters if parameter.required],
            "additionalProperties": False,
        }

    def planner_spec(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "side_effect": self.side_effect,
            "requires_confirmation": self.requires_confirmation,
            "version": self.version,
        }


@dataclass
class ToolResult:
    tool_name: str
    tool_version: str
    status: ToolStatus
    data: Dict[str, Any] = field(default_factory=dict)
    args: Dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    latency_ms: int = 0
    attempts: int = 1

    def to_dict(self) -> Dict[str, Any]:
        # ``tool`` and flattened data preserve the public contract consumed by
        # the response generator and frontend while exposing a typed envelope.
        payload = {
            "tool": self.tool_name,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "status": self.status,
            "data": self.data,
            "args": self.args,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "latency_ms": self.latency_ms,
            "attempts": self.attempts,
        }
        for key, value in self.data.items():
            payload.setdefault(key, value)
        if self.error_message:
            payload.setdefault("message", self.error_message)
        return payload


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition, *, replace: bool = False) -> None:
        if definition.name in self._tools and not replace:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def names(self) -> set[str]:
        return set(self._tools)

    def planner_specs(self) -> List[Dict[str, Any]]:
        return [tool.planner_spec() for tool in self.list_tools()]

    def validate_args(self, definition: ToolDefinition, args: Mapping[str, Any] | None) -> Dict[str, Any]:
        supplied = dict(args or {})
        allowed = {parameter.name: parameter for parameter in definition.parameters}
        unexpected = sorted(set(supplied) - set(allowed))
        if unexpected:
            raise ValueError(f"Unexpected parameters: {', '.join(unexpected)}")
        normalized: Dict[str, Any] = {}
        missing = []
        for name, parameter in allowed.items():
            value = supplied.get(name, parameter.default)
            if parameter.required and (value is None or str(value).strip() == ""):
                missing.append(name)
                continue
            if value is not None:
                if not _matches_json_type(value, parameter.type):
                    raise ValueError(f"Parameter {name} must be {parameter.type}")
                normalized[name] = value
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")
        return normalized

    def validate_output(self, definition: ToolDefinition, data: Mapping[str, Any]) -> None:
        schema = dict(definition.output_schema or {})
        missing = [key for key in schema.get("required", []) if key not in data]
        if missing:
            raise ToolOutputError(f"Missing output fields: {', '.join(missing)}")
        for key, property_schema in dict(schema.get("properties") or {}).items():
            if key not in data or not isinstance(property_schema, Mapping):
                continue
            expected = property_schema.get("type")
            if expected and not _matches_json_type(data[key], str(expected)):
                raise ToolOutputError(f"Output field {key} must be {expected}")

    def execute(
        self,
        name: str,
        args: Mapping[str, Any] | None,
        *,
        granted_permissions: Iterable[str] = ("support:read",),
        confirmed: bool = False,
    ) -> ToolResult:
        started = time.perf_counter()
        definition = self.get(name)
        if definition is None:
            return ToolResult(
                tool_name=name,
                tool_version="unknown",
                status="error",
                args=dict(args or {}),
                error_code="tool_not_found",
                error_message=f"未知工具: {name}",
            )

        granted = set(granted_permissions)
        if not set(definition.permissions).issubset(granted):
            return ToolResult(
                tool_name=name,
                tool_version=definition.version,
                status="permission_denied",
                args=dict(args or {}),
                error_code="permission_denied",
                error_message="当前执行上下文没有工具所需权限",
            )
        if definition.requires_confirmation and not confirmed:
            return ToolResult(
                tool_name=name,
                tool_version=definition.version,
                status="permission_denied",
                args=dict(args or {}),
                error_code="confirmation_required",
                error_message="该工具具有副作用，执行前需要人工确认",
            )

        try:
            normalized = self.validate_args(definition, args)
        except ValueError as exc:
            return ToolResult(
                tool_name=name,
                tool_version=definition.version,
                status="missing_args",
                args=dict(args or {}),
                error_code="invalid_arguments",
                error_message=str(exc),
            )

        attempts = max(1, definition.retries + 1)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"tool-{definition.name}")
            try:
                future = executor.submit(definition.handler, **normalized)
                data = future.result(timeout=definition.timeout_seconds)
                if not isinstance(data, Mapping):
                    raise ToolOutputError("Tool output must be an object")
                self.validate_output(definition, data)
                raw_status = str(data.get("status") or "ok")
                status: ToolStatus = raw_status if raw_status in {
                    "ok", "not_found", "missing_args", "error", "timeout", "permission_denied"
                } else "ok"  # type: ignore[assignment]
                error_message = str(data.get("message") or "") or None if status != "ok" else None
                return ToolResult(
                    tool_name=name,
                    tool_version=definition.version,
                    status=status,
                    data={key: value for key, value in data.items() if key != "status"},
                    args=normalized,
                    error_code=None if status == "ok" else status,
                    error_message=error_message,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    attempts=attempt,
                )
            except FutureTimeoutError:
                last_error = TimeoutError(
                    f"Tool {definition.name} exceeded {definition.timeout_seconds:g}s timeout"
                )
            except Exception as exc:  # pragma: no cover - defensive boundary
                last_error = exc
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        timed_out = isinstance(last_error, TimeoutError)
        invalid_output = isinstance(last_error, ToolOutputError)
        return ToolResult(
            tool_name=name,
            tool_version=definition.version,
            status="timeout" if timed_out else "error",
            args=normalized,
            error_code="tool_timeout" if timed_out else "invalid_tool_output" if invalid_output else "execution_error",
            error_message=str(last_error or "工具执行失败"),
            latency_ms=int((time.perf_counter() - started) * 1000),
            attempts=attempts,
        )
