// FastAPI 공개 API 클라이언트.
// 개발 기본값은 로컬 FastAPI(http://localhost:8000). 배포 시 VITE_API_BASE 로 덮어쓴다.
import type { SkillItem, MapItem, RegionSkillItem, SigunguItem, RelatedSkillItem, TrendItem, PayRankItem, SkillStat, Meta, Career } from './types'
import { ALL_SKILL } from './types'

// 전체 센티넬은 API 파라미터에서 생략(=전체 공고).
const realSkill = (s: string | undefined) => (s === ALL_SKILL ? undefined : s)

const BASE = (import.meta.env.VITE_API_BASE ?? 'http://localhost:8000').replace(/\/+$/, '')

type Params = Record<string, string | number | undefined>

async function get<T>(path: string, params?: Params): Promise<T> {
  const url = new URL(BASE + path)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`)
  return (await res.json()) as T
}

export const fetchSkills = (limit = 300) =>
  get<SkillItem[]>('/api/skills', { limit })

export const fetchMap = (skill: string, career: Career) =>
  get<MapItem[]>('/api/map', { skill: realSkill(skill), career })

export const fetchRegion = (sido: string, career: Career, sigungu?: string, limit = 15) =>
  get<RegionSkillItem[]>('/api/region', { sido, sigungu, career, limit })

export const fetchDrilldown = (sido: string, skill: string, career: Career) =>
  get<SigunguItem[]>('/api/drilldown', { sido, skill: realSkill(skill), career })

export const fetchCooccur = (skill: string, career: Career, limit = 10) =>
  get<RelatedSkillItem[]>('/api/cooccur', { skill, career, limit })

export const fetchTrend = (skill: string | undefined, career: Career) =>
  get<TrendItem[]>('/api/trend', { skill, career })

export const fetchPayRanking = (career: Career, limit = 15, minN = 50) =>
  get<PayRankItem[]>('/api/pay/ranking', { career, limit, min_n: minN })

export const fetchSkillStat = (skill: string, career: Career) =>
  get<SkillStat | null>('/api/skill/stat', { skill, career })

export const fetchMeta = () => get<Meta>('/api/meta')
