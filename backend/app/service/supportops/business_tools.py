"""Mock business tools the agent can invoke (order / logistics / refund).

These are deliberately deterministic mocks: results derive from a hash of the
order id against a fixed base date, so the same input always produces the
same output — demos are reproducible and unit-testable. Swapping a mock for a
real API call keeps the same contract: ``{"tool", "args", "status", ...}``.

Conventions:
- order ids look like ``ORD`` + digits (case-insensitive); other ids are
  accepted but normalized.
- ids whose digits end with ``00`` simulate "order not found", so the
  not-found path is reachable deterministically.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from typing import Any, Dict, List, Optional

from service.supportops.tool_runtime import ToolDefinition, ToolParameter, ToolRegistry

# Fixed base date keeps outputs stable across runs (no wall-clock dependency).
_BASE_DATE = datetime.date(2026, 1, 1)

_ORDER_ID_RE = re.compile(r"\b(ORD[-_]?\d{4,})\b", re.IGNORECASE)
_FALLBACK_ID_RE = re.compile(r"(?:订单号?|单号|order)\s*[:：#]?\s*([A-Za-z0-9-]{6,20})", re.IGNORECASE)

def extract_order_id(text: str) -> Optional[str]:
    """Pull an order id out of free text; None when nothing plausible found."""
    match = _ORDER_ID_RE.search(text or "")
    if match:
        return match.group(1).upper().replace("_", "-")
    match = _FALLBACK_ID_RE.search(text or "")
    if match:
        return match.group(1).upper()
    return None


def _digest(order_id: str) -> bytes:
    return hashlib.blake2b(order_id.upper().encode("utf-8"), digest_size=8).digest()


def _not_found(order_id: str) -> bool:
    digits = re.sub(r"\D", "", order_id)
    return digits.endswith("00")


def _date(offset_days: int) -> str:
    return (_BASE_DATE + datetime.timedelta(days=offset_days)).isoformat()


def query_order(order_id: str) -> Dict[str, Any]:
    if _not_found(order_id):
        return {"status": "not_found", "message": f"订单 {order_id} 不存在，请核对订单号"}
    d = _digest(order_id)
    statuses = ["待发货", "已发货", "已签收", "已取消"]
    payment_statuses = ["已支付", "已支付", "已支付", "支付异常"]
    idx = d[0] % 4
    return {
        "status": "ok",
        "order_id": order_id,
        "order_status": statuses[idx],
        "payment_status": payment_statuses[d[1] % 4],
        "amount_cny": round(20 + (d[2] * 7 + d[3]) % 980 + d[4] / 256, 2),
        "created_at": _date(d[5] % 28),
    }


def query_logistics(order_id: str) -> Dict[str, Any]:
    if _not_found(order_id):
        return {"status": "not_found", "message": f"订单 {order_id} 不存在，请核对订单号"}
    d = _digest(order_id)
    carriers = ["顺丰速运", "中通快递", "圆通速递", "京东物流"]
    stages = [
        ("已揽收", "始发地分拨中心"),
        ("运输中", "区域转运中心"),
        ("派送中", "目的地网点"),
        ("已签收", "收件地址"),
    ]
    progress = d[0] % 4
    base = d[5] % 25
    checkpoints = [
        {"time": _date(base + i), "status": stage, "location": location}
        for i, (stage, location) in enumerate(stages[: progress + 1])
    ]
    return {
        "status": "ok",
        "order_id": order_id,
        "carrier": carriers[d[1] % 4],
        "tracking_no": f"TRK{int.from_bytes(d[2:6], 'big') % 10**10:010d}",
        "current_status": stages[progress][0],
        "checkpoints": checkpoints,
    }


def check_refund_eligibility(order_id: str) -> Dict[str, Any]:
    if _not_found(order_id):
        return {"status": "not_found", "message": f"订单 {order_id} 不存在，请核对订单号"}
    d = _digest(order_id)
    days_since_receipt = d[0] % 14
    window_days = 7
    eligible = days_since_receipt <= window_days
    return {
        "status": "ok",
        "order_id": order_id,
        "eligible": eligible,
        "days_since_receipt": days_since_receipt,
        "window_days": window_days,
        "reason": "在七天无理由退款窗口内，可自动发起退款"
        if eligible
        else "超出七天退款窗口，需人工审核特殊退款申请",
    }


ORDER_ID_PARAMETER = ToolParameter(
    name="order_id",
    type="string",
    description="订单号，如 ORD123456",
)


tool_registry = ToolRegistry()
for definition in (
    ToolDefinition(
        name="query_order",
        description="查询订单状态、金额与支付状态。",
        handler=query_order,
        parameters=(ORDER_ID_PARAMETER,),
        output_schema={"type": "object", "required": ["order_status", "payment_status"]},
        permissions=("support:read",),
    ),
    ToolDefinition(
        name="query_logistics",
        description="查询订单的物流轨迹与最新状态。",
        handler=query_logistics,
        parameters=(ORDER_ID_PARAMETER,),
        output_schema={"type": "object", "required": ["current_status", "checkpoints"]},
        permissions=("support:read",),
    ),
    ToolDefinition(
        name="check_refund_eligibility",
        description="只读检查订单是否在退款窗口内；不会发起退款。",
        handler=check_refund_eligibility,
        parameters=(ORDER_ID_PARAMETER,),
        output_schema={"type": "object", "required": ["eligible", "window_days"]},
        permissions=("support:read",),
    ),
):
    tool_registry.register(definition)


# Compatibility exports are generated from the registry, eliminating the old
# hand-maintained split between specs, names, and handlers.
TOOL_SPECS: List[Dict[str, Any]] = tool_registry.planner_specs()
TOOL_NAMES = tool_registry.names()


def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility wrapper over the typed ToolRegistry runtime."""
    return tool_registry.execute(name, args).to_dict()


def tool_specs_prompt() -> str:
    """Render registry-owned JSON schemas for the planner prompt."""
    lines = []
    for spec in tool_registry.planner_specs():
        properties = spec["input_schema"]["properties"]
        args = ", ".join(f"{key}({value.get('description', '')})" for key, value in properties.items())
        safety = "有副作用/需确认" if spec["requires_confirmation"] else "只读"
        lines.append(f"- {spec['name']} v{spec['version']}: {spec['description']} 参数: {args}; {safety}")
    return "\n".join(lines)
