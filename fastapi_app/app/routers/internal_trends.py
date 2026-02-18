from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.skills import get_company_trends, get_skill_trends
from app.schemas.trend import TrendItem

router = APIRouter(
    prefix="/trends",
    tags=["Internal Trends"],
)


@router.get("/companies", response_model=list[TrendItem])
def trend_companies(
    days: int = Query(7, ge=1, le=365),
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_company_trends(db=db, days=days, top=top)


@router.get("/skills", response_model=list[TrendItem])
def trend_skills(
    days: int = Query(7, ge=1, le=365),
    top: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_skill_trends(db=db, days=days, top=top)
