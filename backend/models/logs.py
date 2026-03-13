from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    notion_task_id = Column(String, index=True, nullable=False)
    status = Column(String, default="PENDING")  # PENDING, PLANNING, EXECUTING, COMPLETED, FAILED
    goal = Column(String, nullable=True)
    execution_plan = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to tool calls
    tool_calls = relationship("ToolCallLog", back_populates="agent_run")

class ToolCallLog(Base):
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True, index=True)
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id"), nullable=False)
    tool_name = Column(String, nullable=False)
    tool_input = Column(JSON, nullable=True)
    tool_output = Column(JSON, nullable=True)
    status = Column(String, default="success") # success, failed
    error_message = Column(String, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship to agent run
    agent_run = relationship("AgentRun", back_populates="tool_calls")
