from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
import re

class Event(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    store_id: str = Field(..., min_length=1)
    camera_id: str = Field(..., min_length=1)
    visitor_id: str = Field(...)
    event_type: Literal[
        'ENTRY',
        'EXIT',
        'ZONE_ENTER',
        'ZONE_EXIT',
        'ZONE_DWELL',
        'BILLING_QUEUE_JOIN',
        'BILLING_QUEUE_ABANDON',
        'REENTRY'
    ]
    timestamp: datetime
    zone_id: Optional[str] = None
    dwell_ms: int = Field(default=0, ge=0)
    is_staff: bool = False
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('visitor_id')
    @classmethod
    def validate_visitor_id(cls, v: str) -> str:
        if not re.match(r"^VIS_[a-zA-Z0-9]{12}$", v) and not re.match(r"^VIS_[a-fA-F0-9]+$", v):
            # Allow VIS_ followed by standard alphanumeric hashes or hex values
            if not v.startswith("VIS_"):
                raise ValueError("visitor_id must start with 'VIS_'")
        return v

    class Config:
        validate_assignment = True
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "store_id": "S001",
                "camera_id": "CAM_A",
                "visitor_id": "VIS_abc123xyz789",
                "event_type": "ENTRY",
                "timestamp": "2024-01-15T10:30:15Z",
                "zone_id": None,
                "dwell_ms": 0,
                "is_staff": False,
                "confidence": 0.95,
                "metadata": {}
            }
        }
