import json
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional

from openai import OpenAI

from service.supportops.api_key_context import get_runtime_config_value


PLACEHOLDER_KEYS = {
    "",
    "your_api_key",
    "your-dashscope-api-key",
    "your_dashscope_api_key",
    "sk-your-real-dashscope-api-key",
}


def clean_env_value(name: str, default: str = "") -> str:
    value = get_runtime_config_value(name)
    if value is None:
        value = os.getenv(name, default) or ""
    return value.strip().strip('"').strip("'")


def has_valid_dashscope_key(api_key: Optional[str] = None) -> bool:
    value = (api_key if api_key is not None else clean_env_value("DASHSCOPE_API_KEY")).strip()
    lowered = value.lower()
    return bool(value) and lowered not in PLACEHOLDER_KEYS and not lowered.startswith("your_")


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def safe_json_loads(value: Any, default: Optional[Any] = None) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return default

    text = str(value).strip()
    if not text:
        return default

    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    candidates = [text]
    obj_match = re.search(r"(\{[\s\S]*\})", text)
    arr_match = re.search(r"(\[[\s\S]*\])", text)
    if obj_match:
        candidates.append(obj_match.group(1))
    if arr_match:
        candidates.append(arr_match.group(1))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return default


def call_json_llm(prompt: str, default: Dict[str, Any]) -> Dict[str, Any]:
    api_key = clean_env_value("DASHSCOPE_API_KEY")
    base_url = clean_env_value("DASHSCOPE_BASE_URL")
    if not has_valid_dashscope_key(api_key):
        return default

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        completion = client.chat.completions.create(
            model=clean_env_value("SUPPORTOPS_MODEL", "qwen-plus"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            stream=False,
            timeout=30,
        )
        content = completion.choices[0].message.content if completion.choices else ""
        parsed = safe_json_loads(content, default)
        return parsed if isinstance(parsed, dict) else default
    except Exception:
        return default


def normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_question(value: Any) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"[，。！？、,.!?;；:：\"'“”‘’（）()\[\]{}<>《》]", "", text)
    return text


def normalize_label(value: Any, default: str = "general") -> str:
    text = normalize_text(value).lower()
    if not text:
        return default
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff]", "", text)
    return text or default


def compact(data: Any, limit: int = 1800) -> str:
    text = json_dumps(data)
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def sse_message(payload: Dict[str, Any]) -> str:
    return f"event: message\ndata: {json_dumps(payload)}\n\n"


def chunk_text(text: str, size: int = 18) -> Iterable[str]:
    for index in range(0, len(text), size):
        yield text[index:index + size]


def simple_similarity(left: str, right: str) -> float:
    left_norm = normalize_question(left)
    right_norm = normalize_question(right)
    if not left_norm or not right_norm:
        return 0.0
    ratio = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_terms = set(left_norm.split())
    right_terms = set(right_norm.split())
    if left_terms and right_terms:
        overlap = len(left_terms & right_terms) / max(len(left_terms | right_terms), 1)
        return round(max(ratio, overlap), 4)
    return round(ratio, 4)


def keyword_category_intent(question: str) -> Dict[str, Any]:
    q = normalize_question(question)
    rules = [
        ("refund", "refund_request", ["退款", "退钱", "refund", "chargeback"]),
        ("payment", "payment_failed", ["支付失败", "扣款", "付款", "payment", "paid", "charge"]),
        ("account", "account_security", ["登录", "密码", "账号", "账户", "盗号", "login", "password", "account"]),
        ("privacy", "privacy_request", ["隐私", "个人信息", "泄露", "privacy", "personal data"]),
        ("complaint", "complaint", ["投诉", "差评", "生气", "愤怒", "complaint", "angry"]),
        ("technical", "technical_issue", ["报错", "打不开", "无法使用", "bug", "error", "failed", "crash"]),
        ("delivery", "delivery_status", ["物流", "快递", "发货", "收货", "delivery", "shipping"]),
        ("product", "product_inquiry", ["说明", "功能", "怎么用", "产品", "feature", "how to"]),
    ]
    for category, intent, keywords in rules:
        if any(keyword in q for keyword in keywords):
            return {
                "category": category,
                "intent": intent,
                "confidence": 0.72,
                "reason": f"命中关键词规则：{category}/{intent}",
            }
    return {
        "category": "general",
        "intent": "general_inquiry",
        "confidence": 0.45,
        "reason": "未命中明确业务关键词，使用通用咨询兜底。",
    }


RISK_RULES = {
    "complaint": ["投诉", "差评", "生气", "愤怒", "complaint", "angry", "unacceptable"],
    "refund": ["退款", "退钱", "refund", "chargeback"],
    "payment_failed": ["支付失败", "扣款失败", "重复扣款", "payment failed", "double charged"],
    "privacy": ["隐私", "个人信息", "身份证", "手机号", "泄露", "privacy", "personal data"],
    "account_security": ["盗号", "账号安全", "密码泄露", "无法登录", "account hacked", "stolen"],
    "legal": ["律师", "起诉", "法律", "赔偿", "legal", "lawsuit", "sue"],
    "strong_negative": ["太差", "垃圾", "再也不用", "愤怒", "气死", "terrible", "furious"],
    "human_request": ["转人工", "人工客服", "真人客服", "找人工", "human agent", "real person", "speak to a human"],
}


def match_risk_rules(question: str) -> List[str]:
    q = normalize_question(question)
    matched = []
    for rule, keywords in RISK_RULES.items():
        if any(keyword in q for keyword in keywords):
            matched.append(rule)
    return matched


def extract_known_labels(similar_tickets: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    labels = []
    seen = set()
    for item in similar_tickets:
        category = item.get("category") or "general"
        intent = item.get("intent") or "general_inquiry"
        key = (category, intent)
        if key in seen:
            continue
        labels.append({"category": category, "intent": intent})
        seen.add(key)
    return labels[:40]
