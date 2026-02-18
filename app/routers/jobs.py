# app/routers/jobs.py
from fastapi import APIRouter
from app.schemas.job import JobOut

router = APIRouter()

@router.get("/test", response_model=JobOut)
def test_job():
    return {
        "id": 1,
        "title": "백엔드 개발자",
        "company": "테스트회사",
        "location": "서울"
    }
