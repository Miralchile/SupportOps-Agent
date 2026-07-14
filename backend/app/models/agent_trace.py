from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from sqlalchemy.sql import func

from models.base import Base


class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    tool_name = Column(String(255), nullable=False)
    tool_input = Column(Text)
    tool_output = Column(Text)
    latency_ms = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="success")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
