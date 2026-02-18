from datetime import date

from pydantic import BaseModel


class SkillItem(BaseModel):
    skill: str
    total_cnt: int
    rank_no: int


class MapItem(BaseModel):
    sido: str
    count: int
    region_total: int
    density: float  # 시도 전체 공고 대비 해당 스킬 비율(%)


class RegionSkillItem(BaseModel):
    skill: str
    count: int


class SigunguItem(BaseModel):
    sigungu: str
    count: int


class RelatedSkillItem(BaseModel):
    skill: str
    count: int
    pct: float   # 기준 스킬 공고 중 이 스킬도 함께 요구한 비율(%)
    lift: float  # P(rel|skill)/P(rel). 1=독립, >1=양의 연관(범용스킬 편향보정)


class TrendItem(BaseModel):
    period: date  # 주 시작일(월요일)
    cnt: int      # 해당 주 게시 공고 수


class PayRankItem(BaseModel):
    skill: str
    pay_n: int    # 연봉 표본 수
    pay_p25: int  # 만원
    pay_p50: int  # 중앙값(만원)
    pay_p75: int
    pay_avg: int


class SkillStatItem(BaseModel):
    skill: str
    career_band: str
    # 경력
    career_n: int
    career_avg: float | None
    junior_cnt: int   # 0-2년
    mid_cnt: int      # 3-5년
    senior_cnt: int   # 6년+
    # 급여 (연봉 하한, 만원). 표본 부족 시 None
    pay_n: int
    pay_p25: int | None
    pay_p50: int | None
    pay_p75: int | None
    pay_avg: int | None
