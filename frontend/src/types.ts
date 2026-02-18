// FastAPI(/api) 응답 스키마와 1:1 대응 — fastapi_app/app/schemas/region.py

export type Career = 'all' | 'junior' | 'senior'

/** 전역 스킬 선택에서 '전체 공고(스킬 무관)'를 뜻하는 센티넬. API 로는 skill 파라미터를 생략한다. */
export const ALL_SKILL = '__all__'
export const skillLabel = (s: string) => (s === ALL_SKILL ? '전체' : s)

/** GET /api/skills */
export interface SkillItem {
  skill: string
  total_cnt: number
  rank_no: number
}

/** GET /api/map */
export interface MapItem {
  sido: string
  count: number
  region_total: number
  /** 시도 전체 공고 대비 해당 스킬 비율(%) */
  density: number
}

/** GET /api/region */
export interface RegionSkillItem {
  skill: string
  count: number
}

/** GET /api/drilldown */
export interface SigunguItem {
  sigungu: string
  count: number
}

/** GET /api/cooccur — 함께 요구되는 스택 */
export interface RelatedSkillItem {
  skill: string
  count: number
  /** 기준 스킬 공고 중 이 스킬도 함께 요구한 비율(%) */
  pct: number
  /** P(rel|skill)/P(rel). 1=독립, >1=양의 연관(범용스킬 편향보정) */
  lift: number
}

/** GET /api/trend — 게시일 기준 주별 공고 추이 */
export interface TrendItem {
  /** 주 시작일(월요일) YYYY-MM-DD */
  period: string
  /** 해당 주 게시 공고 수 */
  cnt: number
}

/** GET /api/pay/ranking — 연봉(하한 중앙값) 상위 스킬 */
export interface PayRankItem {
  skill: string
  /** 연봉 표본 수 */
  pay_n: number
  /** 만원 */
  pay_p25: number
  /** 중앙값(만원) */
  pay_p50: number
  pay_p75: number
  pay_avg: number
}

/** GET /api/skill/stat — 선택 스킬 급여/경력 상세 (없으면 null) */
export interface SkillStat {
  skill: string
  career_band: Career
  /** career_min 있는 공고 수 */
  career_n: number
  /** 평균 요구연차 */
  career_avg: number | null
  junior_cnt: number  // 0-2년
  mid_cnt: number     // 3-5년
  senior_cnt: number  // 6년+
  /** 연봉 표본 수 */
  pay_n: number
  pay_p25: number | null
  pay_p50: number | null
  pay_p75: number | null
  pay_avg: number | null
}

/** GET /api/meta (key/value 사전) */
export interface Meta {
  built_at?: string
  unique_jobs?: string
  skill_count?: string
  [k: string]: string | undefined
}
