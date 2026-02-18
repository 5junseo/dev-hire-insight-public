from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class JobOut(BaseModel):
    id: int
    company: Optional[str]
    title: str
    url: str
    apply_type: Optional[str]
    skills: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
