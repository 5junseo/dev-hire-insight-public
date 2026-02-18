from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.jobs import get_jobs
from app.schemas.job import JobOut

router = APIRouter(
    prefix="/jobs",
    tags=["Internal Jobs"],
)


@router.get("", response_model=list[JobOut])
def list_jobs(
    skill: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return get_jobs(
        db=db,
        skill=skill,
        limit=limit,
        offset=offset,
    )