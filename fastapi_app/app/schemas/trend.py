from pydantic import BaseModel

class TrendItem(BaseModel):
    key: str
    count: int
