import base64
import hashlib
import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from cryptography.fernet import Fernet, InvalidToken
from openai import OpenAI
from sqlalchemy.orm import Session

from models.support_api_key import SupportApiKey
from schemas.supportops import ApiKeyCreate, ApiKeyResponse, ApiKeyTestRequest, ApiKeyTestResponse, ApiKeyUpdate

ENCRYPTED_PREFIX = "fernet:"
DASHSCOPE_PROVIDER = "dashscope"
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_CHAT_MODEL = "qwen-plus"
DASHSCOPE_EMBEDDING_MODEL = "text-embedding-v3"


def _clean(value: str | None, default: str = "") -> str:
    text = str(value or default).strip().strip('"').strip("'")
    return text


def _ensure_dashscope_provider(provider: str | None = DASHSCOPE_PROVIDER) -> str:
    normalized = _clean(provider, DASHSCOPE_PROVIDER).lower()
    if normalized != DASHSCOPE_PROVIDER:
        raise HTTPException(
            status_code=400,
            detail="当前版本仅支持 DashScope / 阿里云百炼 API Key。DeepSeek 可用于对话模型，但不能完整覆盖本项目的 Embedding 检索链路。",
        )
    return DASHSCOPE_PROVIDER


def _fernet() -> Fernet:
    secret = os.getenv("JWT_SECRET_KEY", "supportops_local_secret") + ":supportops_api_keys"
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_api_key(api_key: str) -> str:
    raw = _clean(api_key)
    if raw.startswith(ENCRYPTED_PREFIX):
        return raw
    return ENCRYPTED_PREFIX + _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_api_key(api_key: str) -> str:
    value = _clean(api_key)
    if not value.startswith(ENCRYPTED_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(ENCRYPTED_PREFIX):].encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""


def mask_api_key(api_key: str) -> str:
    key = decrypt_api_key(api_key)
    if len(key) <= 10:
        return "*" * max(len(key), 6)
    return f"{key[:6]}...{key[-4:]}"


def to_api_key_response(record: SupportApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=record.id,
        name=record.name,
        provider=record.provider,
        masked_api_key=mask_api_key(record.api_key),
        base_url=record.base_url,
        model=record.model,
        embedding_model=record.embedding_model,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _deactivate_other_keys(db: Session, user_id: str, keep_id: Optional[int] = None) -> None:
    query = db.query(SupportApiKey).filter(SupportApiKey.user_id == user_id)
    if keep_id is not None:
        query = query.filter(SupportApiKey.id != keep_id)
    query.update({"is_active": False}, synchronize_session=False)


def list_api_keys(db: Session, user_id: str) -> List[ApiKeyResponse]:
    records = (
        db.query(SupportApiKey)
        .filter(SupportApiKey.user_id == user_id, SupportApiKey.provider == DASHSCOPE_PROVIDER)
        .order_by(SupportApiKey.is_active.desc(), SupportApiKey.updated_at.desc(), SupportApiKey.id.desc())
        .all()
    )
    return [to_api_key_response(record) for record in records]


def create_api_key(db: Session, user_id: str, payload: ApiKeyCreate) -> ApiKeyResponse:
    api_key = _clean(payload.api_key)
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    provider = _ensure_dashscope_provider(payload.provider)
    if payload.is_active:
        _deactivate_other_keys(db, user_id)

    record = SupportApiKey(
        user_id=user_id,
        name=_clean(payload.name, "DashScope") or "DashScope",
        provider=provider,
        api_key=encrypt_api_key(api_key),
        base_url=_clean(payload.base_url, DASHSCOPE_BASE_URL),
        model=_clean(payload.model, DASHSCOPE_CHAT_MODEL),
        embedding_model=_clean(payload.embedding_model, DASHSCOPE_EMBEDDING_MODEL),
        is_active=payload.is_active,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return to_api_key_response(record)


def update_api_key(db: Session, user_id: str, key_id: int, payload: ApiKeyUpdate) -> ApiKeyResponse:
    record = db.query(SupportApiKey).filter(SupportApiKey.user_id == user_id, SupportApiKey.id == key_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    _ensure_dashscope_provider(record.provider)

    if payload.name is not None:
        record.name = _clean(payload.name, record.name) or record.name
    if payload.api_key is not None:
        api_key = _clean(payload.api_key)
        if not api_key:
            raise HTTPException(status_code=400, detail="API Key 不能为空")
        record.api_key = encrypt_api_key(api_key)
    if payload.base_url is not None:
        record.base_url = _clean(payload.base_url, record.base_url)
    if payload.model is not None:
        record.model = _clean(payload.model, record.model)
    if payload.embedding_model is not None:
        record.embedding_model = _clean(payload.embedding_model, record.embedding_model)
    if payload.is_active is not None:
        record.is_active = payload.is_active
        if payload.is_active:
            _deactivate_other_keys(db, user_id, keep_id=record.id)

    db.commit()
    db.refresh(record)
    return to_api_key_response(record)


def activate_api_key(db: Session, user_id: str, key_id: int) -> ApiKeyResponse:
    return update_api_key(db, user_id, key_id, ApiKeyUpdate(is_active=True))


def delete_api_key(db: Session, user_id: str, key_id: int) -> Dict[str, Any]:
    record = db.query(SupportApiKey).filter(SupportApiKey.user_id == user_id, SupportApiKey.id == key_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    db.delete(record)
    db.commit()
    return {"status": "success", "message": "API Key 已删除"}


def get_active_api_key_config(db: Session, user_id: str) -> Optional[Dict[str, str]]:
    record = (
        db.query(SupportApiKey)
        .filter(
            SupportApiKey.user_id == user_id,
            SupportApiKey.provider == DASHSCOPE_PROVIDER,
            SupportApiKey.is_active.is_(True),
        )
        .order_by(SupportApiKey.updated_at.desc(), SupportApiKey.id.desc())
        .first()
    )
    if not record:
        return None
    return {
        "provider": record.provider,
        "api_key": decrypt_api_key(record.api_key),
        "base_url": record.base_url,
        "model": record.model,
        "embedding_model": record.embedding_model,
    }


def _run_dashscope_probe(api_key: str, base_url: str, model: str, embedding_model: str) -> ApiKeyTestResponse:
    if not _clean(api_key):
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    base_url = _clean(base_url, DASHSCOPE_BASE_URL)
    model = _clean(model, DASHSCOPE_CHAT_MODEL)
    embedding_model = _clean(embedding_model, DASHSCOPE_EMBEDDING_MODEL)
    client = OpenAI(api_key=api_key, base_url=base_url)
    details: Dict[str, Any] = {
        "provider": DASHSCOPE_PROVIDER,
        "base_url": base_url,
        "model": model,
        "embedding_model": embedding_model,
    }

    chat_ok = False
    embedding_ok = False

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "请只回复 OK"}],
            stream=False,
            timeout=20,
        )
        content = completion.choices[0].message.content if completion.choices else ""
        chat_ok = bool(content)
    except Exception as exc:
        details["chat_error"] = str(exc)

    try:
        completion = client.embeddings.create(
            model=embedding_model,
            input="SupportOps Agent API key test",
            dimensions=1024,
            encoding_format="float",
            timeout=20,
        )
        vector = completion.data[0].embedding if completion.data else None
        embedding_ok = isinstance(vector, list) and len(vector) > 0
        if embedding_ok:
            details["embedding_dim"] = len(vector)
    except Exception as exc:
        details["embedding_error"] = str(exc)

    if chat_ok and embedding_ok:
        return ApiKeyTestResponse(
            status="success",
            chat_ok=True,
            embedding_ok=True,
            message="API Key 可用，对话模型和 Embedding 模型均验证通过。",
            details=details,
        )

    failed_parts = []
    if not chat_ok:
        failed_parts.append("对话模型")
    if not embedding_ok:
        failed_parts.append("Embedding 模型")
    return ApiKeyTestResponse(
        status="failed",
        chat_ok=chat_ok,
        embedding_ok=embedding_ok,
        message=f"{'、'.join(failed_parts)}验证失败，请检查 API Key、Base URL、模型名和账号权限。",
        details=details,
    )


def test_api_key_payload(payload: ApiKeyTestRequest) -> ApiKeyTestResponse:
    return _run_dashscope_probe(
        api_key=_clean(payload.api_key),
        base_url=payload.base_url,
        model=payload.model,
        embedding_model=payload.embedding_model,
    )


def test_saved_api_key(db: Session, user_id: str, key_id: int) -> ApiKeyTestResponse:
    record = db.query(SupportApiKey).filter(SupportApiKey.user_id == user_id, SupportApiKey.id == key_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    _ensure_dashscope_provider(record.provider)
    return _run_dashscope_probe(
        api_key=decrypt_api_key(record.api_key),
        base_url=record.base_url,
        model=record.model,
        embedding_model=record.embedding_model,
    )
