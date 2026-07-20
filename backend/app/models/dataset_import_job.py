from sqlalchemy import Column, Integer, JSON, String, TIMESTAMP
from sqlalchemy.sql import func

from models.base import Base


class DatasetImportJob(Base):
    __tablename__ = "dataset_import_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    dataset_name = Column(String(120), nullable=False, index=True)
    dataset_version = Column(String(80), nullable=False, default="unknown")
    source_filename = Column(String(500), nullable=False)
    source_type = Column(String(32), nullable=False, default="unknown", index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    checksum = Column(String(64), nullable=False)
    total_rows = Column(Integer, nullable=False, default=0)
    accepted_rows = Column(Integer, nullable=False, default=0)
    rejected_rows = Column(Integer, nullable=False, default=0)
    duplicate_rows = Column(Integer, nullable=False, default=0)
    pii_redacted_rows = Column(Integer, nullable=False, default=0)
    indexed_rows = Column(Integer, nullable=False, default=0)
    split_counts = Column(JSON, nullable=False, default=dict)
    import_options = Column(JSON, nullable=False, default=dict)
    errors = Column(JSON, nullable=False, default=list)
    started_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    completed_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
