from sqlalchemy import Boolean, Column, Integer, String, TIMESTAMP, Text
from sqlalchemy.sql import func

from models.base import Base


class SupportApiKey(Base):
    __tablename__ = "supportops_api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    name = Column(String(120), nullable=False, default="DashScope")
    provider = Column(String(50), nullable=False, default="dashscope", index=True)
    api_key = Column(Text, nullable=False)
    base_url = Column(String(500), nullable=False, default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = Column(String(120), nullable=False, default="qwen-plus")
    embedding_model = Column(String(120), nullable=False, default="text-embedding-v3")
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
