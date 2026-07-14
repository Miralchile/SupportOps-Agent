from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
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
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
