# app/schemas/job.py
from pydantic import BaseModel

class JobBase(BaseModel):
    title: str
    company: str
    location: str

class JobOut(JobBase):
    id: int
