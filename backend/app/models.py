"""
SQLAlchemy Models for Test Run History and Telemetry.
"""

import json
import time
from sqlalchemy import Column, String, Integer, Float, Text, DateTime
from backend.app.database import Base


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(String(64), primary_key=True, index=True)
    prompt = Column(Text, nullable=False)
    test_type = Column(String(32), index=True, default="baseline")
    status = Column(String(32), index=True, default="PENDING") # PENDING, GENERATING, RUNNING, COMPLETED, FAILED
    
    target_url = Column(String(255), default="http://localhost:8001")
    virtual_users = Column(Integer, default=10)
    duration = Column(String(32), default="30s")
    
    # Serialized JSON blobs
    intent_json = Column(Text, nullable=True)
    synthetic_payloads_json = Column(Text, nullable=True)
    script_content = Column(Text, nullable=True)
    metrics_summary_json = Column(Text, nullable=True)
    ai_report = Column(Text, nullable=True)
    
    created_at = Column(Float, default=time.time)
    completed_at = Column(Float, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "prompt": self.prompt,
            "test_type": self.test_type,
            "status": self.status,
            "target_url": self.target_url,
            "virtual_users": self.virtual_users,
            "duration": self.duration,
            "intent": json.loads(self.intent_json) if self.intent_json else None,
            "synthetic_payloads": json.loads(self.synthetic_payloads_json) if self.synthetic_payloads_json else None,
            "script": self.script_content,
            "metrics": json.loads(self.metrics_summary_json) if self.metrics_summary_json else None,
            "ai_report": self.ai_report,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message
        }
