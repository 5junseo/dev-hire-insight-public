"""
지역 × 스킬 공개 API.

프론트(React 등)가 직접 호출하는 순수 데이터 엔드포인트.
인증/내부키 없음 — 단일 서버 공개 API.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core import mart
from app.schemas.region import (
    SkillItem, MapItem, RegionSkillItem, SigunguItem, RelatedSkillItem, TrendItem,
    PayRankItem, SkillStatItem,
)

router = APIRouter(prefix="/api", tags=["region"])

CAREER = Query("all", pattern="^(all|junior|senior)$", description="all / junior(0-2년) / senior(3년+)")


@router.get("/skills", response_model=list[SkillItem])
def get_skills(limit: int = Query(300, ge=1, le=2000), db: Session = Depends(get_db)):
    """선택 가능한 스킬 목록 + 전국 순위 (드롭다운 채우기)."""
    return mart.list_skills(db, limit)


@router.get("/map", response_model=list[MapItem])
def get_map(
    skill: str | None = Query(None, description="스킬명 (예: python). 없으면 전체 공고 수"),
    career: str = CAREER,
    db: Session = Depends(get_db),
):
    """특정 스킬의 시도별 공고 수 + 밀도 (지도 색칠용). skill 없으면 전체 공고 수."""
    if not skill:
        return mart.map_total(db, career)
    return mart.map_by_skill(db, skill, career)


@router.get("/region", response_model=list[RegionSkillItem])
def get_region(
    sido: str = Query(..., description="시도명 (예: 서울)"),
    sigungu: str | None = Query(None, description="시군구명 (예: 강남구). 없으면 시도 전체"),
    career: str = CAREER,
    limit: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """선택 지역의 인기 스택 순위."""
    return mart.region_skills(db, sido, sigungu, career, limit)


@router.get("/drilldown", response_model=list[SigunguItem])
def get_drilldown(
    sido: str = Query(..., description="시도명"),
    skill: str | None = Query(None, description="스킬명. 없으면 전체 공고 수"),
    career: str = CAREER,
    db: Session = Depends(get_db),
):
    """시도 클릭 시 드릴다운 — 시군구별 공고 수. skill 없으면 전체."""
    if not skill:
        return mart.sigungu_total(db, sido, career)
    return mart.sigungu_by_skill(db, sido, skill, career)


@router.get("/cooccur", response_model=list[RelatedSkillItem])
def get_cooccur(
    skill: str = Query(..., description="기준 스킬명 (예: python)"),
    career: str = CAREER,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """선택 스킬과 함께 요구되는 스택 (전국 동시출현 비율)."""
    return mart.related_skills(db, skill, career, limit)


@router.get("/trend", response_model=list[TrendItem])
def get_trend(
    skill: str | None = Query(None, description="스킬명. 없으면 전체 공고 추이"),
    career: str = CAREER,
    db: Session = Depends(get_db),
):
    """게시일 기준 주별 공고 추이 (시계열). skill 지정 시 그 스킬만."""
    return mart.trend(db, skill, career)


@router.get("/pay/ranking", response_model=list[PayRankItem])
def get_pay_ranking(
    career: str = CAREER,
    limit: int = Query(20, ge=1, le=100),
    min_n: int = Query(30, ge=1, le=1000, description="랭킹 포함 최소 연봉 표본 수"),
    db: Session = Depends(get_db),
):
    """연봉(하한 중앙값) 상위 스킬 랭킹. 표본 min_n 미만 스킬 제외."""
    return mart.pay_ranking(db, career, limit, min_n)


@router.get("/skill/stat", response_model=SkillStatItem | None)
def get_skill_stat(
    skill: str = Query(..., description="스킬명 (예: python)"),
    career: str = CAREER,
    db: Session = Depends(get_db),
):
    """선택 스킬의 급여/경력 상세 통계 (없으면 null)."""
    return mart.skill_stat(db, skill, career)


@router.get("/meta")
def get_meta(db: Session = Depends(get_db)):
    """마트 신선도/규모 (화면 하단 '최종 갱신' 표기)."""
    return mart.meta(db)
