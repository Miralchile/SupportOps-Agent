from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, JSON, String, Text, TIMESTAMP
from sqlalchemy.sql import func

from models.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    instruction = Column(Text, nullable=False)
    category = Column(String(255), nullable=False, index=True)
    intent = Column(String(255), nullable=False, index=True)
    response = Column(Text, nullable=False)
    source = Column(String(255), nullable=False, default="csv")
    source_type = Column(String(32), nullable=False, default="unknown", index=True)
    external_id = Column(String(255), nullable=True)
    conversation_id = Column(String(255), nullable=True, index=True)
    language = Column(String(16), nullable=False, default="unknown")
    dataset_split = Column(String(16), nullable=False, default="unspecified", index=True)
    raw_category = Column(String(255), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    pii_redacted = Column(Boolean, nullable=False, default=False)
    quality_score = Column(Float, nullable=False, default=1.0)
    content_hash = Column(String(64), nullable=True, index=True)
    import_job_id = Column(Integer, ForeignKey("dataset_import_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
