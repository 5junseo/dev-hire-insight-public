import { useEffect, useMemo, useState } from 'react'
import { interpolateYlOrBr } from 'd3-scale-chromatic'
import type { Career, MapItem, Meta, RegionSkillItem, SigunguItem, SkillItem, RelatedSkillItem } from './types'
import { ALL_SKILL, skillLabel } from './types'
import { fetchSkills, fetchMap, fetchRegion, fetchDrilldown, fetchCooccur, fetchMeta } from './api'
import KoreaMap, { type MapDatum } from './components/KoreaMap'
import SkillPicker from './components/SkillPicker'
import CareerToggle from './components/CareerToggle'
import RegionPanel from './components/RegionPanel'
import SkillCooccur from './components/SkillCooccur'
import TrendChart from './components/TrendChart'
import SalaryPanel from './components/SalaryPanel'
import ProfileCard, { type RecItem, type DemandItem } from './components/ProfileCard'
import Legend from './components/Legend'

const PROFILE_KEY = 'devhire.profile'

function loadProfile(): string[] {
  try {
    const raw = localStorage.getItem(PROFILE_KEY)
    return raw ? (JSON.parse(raw) as string[]) : []
  } catch {
    return []
  }
}
import './App.css'

const EMPTY_COLOR = '#efe7d3'

export default function App() {
  const [skills, setSkills] = useState<SkillItem[]>([])
  const [skill, setSkill] = useState(ALL_SKILL)  // 기본: 전체 공고
  const [career, setCareer] = useState<Career>('all')

  const [mapData, setMapData] = useState<MapItem[]>([])
  const [mapLoading, setMapLoading] = useState(false)

  const [selectedSido, setSelectedSido] = useState<string | null>(null)
  const [regionData, setRegionData] = useState<RegionSkillItem[]>([])
  const [regionLoading, setRegionLoading] = useState(false)

  const [drilldown, setDrilldown] = useState<SigunguItem[]>([])
  const [drilldownLoading, setDrilldownLoading] = useState(false)

  const [cooccur, setCooccur] = useState<RelatedSkillItem[]>([])
  const [cooccurLoading, setCooccurLoading] = useState(false)

  const [profile, setProfile] = useState<string[]>(loadProfile)
  const [rec, setRec] = useState<RecItem[]>([])
  const [demand, setDemand] = useState<DemandItem[]>([])
  const [profileLoading, setProfileLoading] = useState(false)

  const [meta, setMeta] = useState<Meta | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 최초: 스킬 목록 + 메타. 기본 선택 스킬 = 전국 1위.
  useEffect(() => {
    fetchSkills()
      .then((rows) => setSkills(rows))  // 기본 선택은 '전체'라 자동 선택 불필요
      .catch((e) => setError(String(e)))
    fetchMeta().then(setMeta).catch(() => {})
  }, [])

  // 스킬/경력 변경 → 지도 재조회.
  useEffect(() => {
    if (!skill) return
    setMapLoading(true)
    fetchMap(skill, career)
      .then((rows) => setMapData(rows))
      .catch((e) => setError(String(e)))
      .finally(() => setMapLoading(false))
  }, [skill, career])

  // 지역/경력 변경 → 그 지역 스택 순위 재조회.
  useEffect(() => {
    if (!selectedSido) return
    setRegionLoading(true)
    fetchRegion(selectedSido, career)
      .then((rows) => setRegionData(rows))
      .catch((e) => setError(String(e)))
      .finally(() => setRegionLoading(false))
  }, [selectedSido, career])

  // 지역/스킬/경력 변경 → 그 스킬의 시군구 분포(드릴다운) 재조회.
  useEffect(() => {
    if (!selectedSido || !skill) {
      setDrilldown([])
      return
    }
    let ignore = false
    setDrilldownLoading(true)
    fetchDrilldown(selectedSido, skill, career)
      .then((rows) => { if (!ignore) setDrilldown(rows) })
      .catch((e) => { if (!ignore) setError(String(e)) })
      .finally(() => { if (!ignore) setDrilldownLoading(false) })
    return () => { ignore = true }
  }, [selectedSido, skill, career])

  // 스킬/경력 변경 → 함께 요구되는 스택(동시출현) 재조회. 전국 기준이라 지역과 무관.
  // 전체 보기에는 동시출현 개념이 없으므로 건너뛴다.
  useEffect(() => {
    if (!skill || skill === ALL_SKILL) {
      setCooccur([])
      return
    }
    let ignore = false
    setCooccurLoading(true)
    fetchCooccur(skill, career, 20)
      .then((rows) => { if (!ignore) setCooccur(rows) })
      .catch(() => { if (!ignore) setCooccur([]) })  // 부가 기능: 실패해도 페이지 전체는 유지
      .finally(() => { if (!ignore) setCooccurLoading(false) })
    return () => { ignore = true }
  }, [skill, career])

  // 프로필 변경 → localStorage 저장.
  useEffect(() => {
    try { localStorage.setItem(PROFILE_KEY, JSON.stringify(profile)) } catch { /* 저장 실패는 무시 */ }
  }, [profile])

  // 프로필/경력 변경 → 맞춤 결과 계산. 기존 엔드포인트(cooccur·map) 재활용, 전부 클라 집계.
  useEffect(() => {
    if (profile.length === 0) {
      setRec([])
      setDemand([])
      return
    }
    let ignore = false
    setProfileLoading(true)
    const owned = new Set(profile)
    Promise.all([
      Promise.all(profile.map((s) => fetchCooccur(s, career, 30).catch(() => []))),
      Promise.all(profile.map((s) => fetchMap(s, career).catch(() => []))),
    ])
      .then(([cooccurLists, mapLists]) => {
        if (ignore) return
        // 추천 스택: 내 스킬들과의 lift 합산(편향보정), 이미 가진 건 제외.
        // pct 대신 lift 를 합해야 git/aws 같은 범용스킬이 추천을 잠식하지 않는다.
        const score = new Map<string, number>()
        const matches = new Map<string, number>()
        for (const list of cooccurLists) {
          for (const it of list) {
            if (owned.has(it.skill)) continue
            score.set(it.skill, (score.get(it.skill) ?? 0) + it.lift)
            matches.set(it.skill, (matches.get(it.skill) ?? 0) + 1)
          }
        }
        const recRows: RecItem[] = [...score.entries()]
          .map(([skill, sc]) => ({ skill, score: sc, matches: matches.get(skill) ?? 1 }))
          .sort((a, b) => b.score - a.score || b.matches - a.matches)
          .slice(0, 15)
        setRec(recRows)

        // 수요 지역: 내 스킬들의 시도별 공고 수 합산.
        const reg = new Map<string, number>()
        for (const list of mapLists) {
          for (const it of list) reg.set(it.sido, (reg.get(it.sido) ?? 0) + it.count)
        }
        const demandRows: DemandItem[] = [...reg.entries()]
          .map(([sido, count]) => ({ sido, count }))
          .filter((d) => d.count > 0)
          .sort((a, b) => b.count - a.count)
          .slice(0, 10)
        setDemand(demandRows)
      })
      .finally(() => { if (!ignore) setProfileLoading(false) })
    return () => { ignore = true }
  }, [profile, career])

  const dataMap = useMemo(() => {
    const m = new Map<string, MapDatum>()
    for (const d of mapData) m.set(d.sido, { count: d.count, density: d.density })
    return m
  }, [mapData])

  const maxCount = useMemo(() => {
    const cs = mapData.map((d) => d.count)
    return cs.length ? Math.max(...cs, 1) : 1
  }, [mapData])

  const colorFor = useMemo(() => {
    return (sido: string) => {
      const d = dataMap.get(sido)
      if (!d || d.count === 0) return EMPTY_COLOR
      // 공고 수 기준 색칠. 서울/경기 편중이 심해 log 로 압축 + 바닥값(0.28)을 둬,
      // 적은 지역도 뚜렷이 색이 들어오게. 순서는 그대로 공고수 순.
      const t = 0.28 + 0.72 * (Math.log(d.count + 1) / Math.log(maxCount + 1))
      return interpolateYlOrBr(t)
    }
  }, [dataMap, maxCount])

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>DevHire Insight</h1>
          <p className="tagline">지역 × 개발 스택 채용 지도</p>
        </div>
        <div className="controls">
          <SkillPicker skills={skills} value={skill} onChange={setSkill} />
          <CareerToggle value={career} onChange={setCareer} />
        </div>
      </header>

      {error && <div className="error-banner">불러오기 실패: {error}</div>}

      <ProfileCard
        skills={skills}
        profile={profile}
        onAdd={(s) => setProfile((p) => (p.includes(s) ? p : [...p, s]))}
        onRemove={(s) => setProfile((p) => p.filter((x) => x !== s))}
        rec={rec}
        demand={demand}
        loading={profileLoading}
        onPickSkill={setSkill}
        onPickRegion={setSelectedSido}
      />

      <TrendChart skill={skill} career={career} skills={skills} />

      <SalaryPanel skill={skill} career={career} onPickSkill={setSkill} />

      <main className="app-main">
        <section className="map-col">
          <div className="map-head">
            <h2>
              <strong>{skillLabel(skill) || '—'}</strong> 시도별 공고 수
            </h2>
            {mapLoading && <span className="loading-dot">갱신 중…</span>}
          </div>
          <KoreaMap
            data={dataMap}
            colorFor={colorFor}
            selectedSido={selectedSido}
            onSelect={setSelectedSido}
          />
          <Legend max={maxCount} interpolate={interpolateYlOrBr} emptyColor={EMPTY_COLOR} />
          {skill !== ALL_SKILL && <SkillCooccur skill={skill} items={cooccur} loading={cooccurLoading} />}
        </section>

        <RegionPanel
          sido={selectedSido}
          items={regionData}
          loading={regionLoading}
          activeSkill={skill}
          onPickSkill={setSkill}
          drilldown={drilldown}
          drilldownLoading={drilldownLoading}
        />
      </main>

      <footer className="app-footer">
        {meta?.built_at && <span>최종 갱신 {meta.built_at}</span>}
        {meta?.unique_jobs && <span>· 공고 {Number(meta.unique_jobs).toLocaleString()}건</span>}
        {meta?.skill_count && <span>· 스킬 {Number(meta.skill_count).toLocaleString()}종</span>}
      </footer>
    </div>
  )
}
