// 스킬별 연봉 · 요구경력 분석.
//   왼쪽: 연봉(제시 하한 중앙값) 상위 스킬 랭킹 — 25~75% 범위 막대 + 중앙값 마커.
//   오른쪽: 선택 스킬 상세 — 연봉 중앙값/범위 + 요구경력 평균/분포(주니어·미들·시니어).
// /api/pay/ranking + /api/skill/stat 자체 조회. 무거운 라이브러리 없이 CSS/SVG.
import { useEffect, useMemo, useState } from 'react'
import { fetchPayRanking, fetchSkillStat } from '../api'
import type { Career, PayRankItem, SkillStat } from '../types'
import { ALL_SKILL } from '../types'

interface Props {
  skill: string
  career: Career
  onPickSkill: (s: string) => void
}

const BAND_LABEL: Record<Career, string> = { all: '전체', junior: '주니어', senior: '시니어' }
const man = (v: number) => v.toLocaleString()          // 만원 표기
const pctOf = (c: number, total: number) => (total ? Math.round((c / total) * 100) : 0) + '%'
const LOW_N = 30  // 이 미만이면 통계 신뢰도 낮다고 표시

export default function SalaryPanel({ skill, career, onPickSkill }: Props) {
  const [ranking, setRanking] = useState<PayRankItem[]>([])
  const [rankLoading, setRankLoading] = useState(false)
  const [stat, setStat] = useState<SkillStat | null>(null)       // 연봉(선택 밴드)
  const [statAll, setStatAll] = useState<SkillStat | null>(null) // 경력 분포(전체 기준)
  const [statLoading, setStatLoading] = useState(false)

  // 연봉 랭킹 (경력 밴드별). 표본 50건+ 스킬만.
  useEffect(() => {
    let ignore = false
    setRankLoading(true)
    fetchPayRanking(career, 15, 50)
      .then((rows) => { if (!ignore) setRanking(rows) })
      .catch(() => { if (!ignore) setRanking([]) })
      .finally(() => { if (!ignore) setRankLoading(false) })
    return () => { ignore = true }
  }, [career])

  // 선택 스킬 상세: 연봉은 선택 밴드, 경력 분포는 전체(밴드로 나누면 순환이라 의미 없음).
  useEffect(() => {
    if (!skill || skill === ALL_SKILL) { setStat(null); setStatAll(null); return }
    let ignore = false
    setStatLoading(true)
    Promise.all([
      fetchSkillStat(skill, career).catch(() => null),
      career === 'all' ? Promise.resolve(null) : fetchSkillStat(skill, 'all').catch(() => null),
    ])
      .then(([s, sAll]) => {
        if (ignore) return
        setStat(s)
        setStatAll(career === 'all' ? s : sAll)
      })
      .finally(() => { if (!ignore) setStatLoading(false) })
    return () => { ignore = true }
  }, [skill, career])

  // 랭킹 막대 공용 급여축 [lo, hi] — 스킬 간 범위 비교가 되도록 500 단위로 맞춤.
  const axis = useMemo(() => {
    if (!ranking.length) return null
    const lo = Math.floor(Math.min(...ranking.map((r) => r.pay_p25)) / 500) * 500
    const hi = Math.ceil(Math.max(...ranking.map((r) => r.pay_p75)) / 500) * 500
    const span = Math.max(1, hi - lo)
    const pct = (v: number) => ((v - lo) / span) * 100
    const ticks: number[] = []
    for (let t = lo; t <= hi; t += 1000) ticks.push(t)
    return { lo, hi, pct, ticks }
  }, [ranking])

  if (!skill) return null

  const dist = statAll  // 경력 분포용(전체 기준)
  const distTotal = dist ? dist.junior_cnt + dist.mid_cnt + dist.senior_cnt : 0

  return (
    <section className="pay">
      <p className="pay-head">
        <strong>연봉 · 요구경력</strong>
        <span className="pay-note"> · 연봉=제시 하한 중앙값(만원) · 표본 50건+ 스킬</span>
      </p>

      <div className="pay-grid">
        {/* ---- 연봉 랭킹 ---- */}
        <div className="pay-rank">
          <p className="pay-sub">연봉 상위 스킬 <em>{BAND_LABEL[career]}</em></p>
          {rankLoading && <div className="pay-empty">불러오는 중…</div>}
          {!rankLoading && !ranking.length && <div className="pay-empty">표본이 충분한 스킬이 없습니다.</div>}
          {!rankLoading && axis && ranking.length > 0 && (
            <>
              <ul className="pay-rank-list">
                {ranking.map((r, i) => {
                  const on = r.skill === skill
                  const l25 = axis.pct(r.pay_p25)
                  const l75 = axis.pct(r.pay_p75)
                  return (
                    <li key={r.skill} className={`pay-rank-row${on ? ' on' : ''}`}>
                      <button
                        type="button"
                        className="pay-rank-name"
                        onClick={() => onPickSkill(r.skill)}
                        title={`표본 ${r.pay_n}건`}
                      >
                        <span className="pay-rank-no">{i + 1}</span>{r.skill}
                      </button>
                      <span className="pay-track">
                        <span className="pay-range" style={{ left: `${l25}%`, width: `${Math.max(1.5, l75 - l25)}%` }} />
                        <span className="pay-med" style={{ left: `${axis.pct(r.pay_p50)}%` }} />
                      </span>
                      <span className="pay-val">{man(r.pay_p50)}</span>
                    </li>
                  )
                })}
              </ul>
              <div className="pay-axis">
                {axis.ticks.map((t) => (
                  <span key={t} className="pay-axis-tick" style={{ left: `${axis.pct(t)}%` }}>{man(t)}</span>
                ))}
              </div>
              <p className="pay-rank-legend">
                <i className="sw sw-range" /> 25~75% 범위 <i className="sw sw-med" /> 중앙값 · 클릭 시 선택
              </p>
            </>
          )}
        </div>

        {/* ---- 선택 스킬 상세 ---- */}
        <div className="pay-detail">
          <p className="pay-sub">{skill === ALL_SKILL ? '스킬 상세' : <><strong>{skill}</strong> 상세</>}</p>
          {skill === ALL_SKILL && (
            <div className="pay-empty">위 랭킹이나 상단에서 스킬을 고르면<br />연봉·요구경력 상세가 표시됩니다.</div>
          )}
          {skill !== ALL_SKILL && statLoading && <div className="pay-empty">불러오는 중…</div>}
          {skill !== ALL_SKILL && !statLoading && (
            <>
              {/* 연봉 */}
              <div className="pay-box">
                <span className="pay-box-label">
                  연봉 중앙값 {career !== 'all' && <em>{BAND_LABEL[career]}</em>}
                </span>
                {stat && stat.pay_p50 != null ? (
                  <>
                    <span className="pay-box-big">{man(stat.pay_p50)}<small>만원</small></span>
                    <span className="pay-box-sub">
                      25~75% {man(stat.pay_p25!)}~{man(stat.pay_p75!)}만원 · 표본 {stat.pay_n.toLocaleString()}건
                      {stat.pay_n < LOW_N && <em className="pay-low"> · 표본 적어 참고용</em>}
                    </span>
                  </>
                ) : (
                  <span className="pay-box-na">연봉 표본 부족 — 급여 공개 공고 10건 미만</span>
                )}
              </div>

              {/* 요구경력 */}
              <div className="pay-box">
                <span className="pay-box-label">평균 요구경력 <span className="pay-note">(전체 공고 기준)</span></span>
                {dist && dist.career_avg != null && distTotal > 0 ? (
                  <>
                    <span className="pay-box-big">{dist.career_avg}<small>년</small></span>
                    <div className="pay-dist" role="img" aria-label="요구경력 분포">
                      {(['junior', 'mid', 'senior'] as const).map((k) => {
                        const c = k === 'junior' ? dist.junior_cnt : k === 'mid' ? dist.mid_cnt : dist.senior_cnt
                        const p = (c / distTotal) * 100
                        return p > 0
                          ? <span key={k} className={`pay-seg pay-seg-${k}`} style={{ width: `${p}%` }} title={`${c.toLocaleString()}건`} />
                          : null
                      })}
                    </div>
                    <div className="pay-dist-legend">
                      <span><i className="sw pay-seg-junior" />주니어 0-2년 {pctOf(dist.junior_cnt, distTotal)}</span>
                      <span><i className="sw pay-seg-mid" />미들 3-5년 {pctOf(dist.mid_cnt, distTotal)}</span>
                      <span><i className="sw pay-seg-senior" />시니어 6년+ {pctOf(dist.senior_cnt, distTotal)}</span>
                    </div>
                    <span className="pay-box-sub">
                      표본 {dist.career_n.toLocaleString()}건
                      {dist.career_n < LOW_N && <em className="pay-low"> · 표본 적어 참고용</em>}
                    </span>
                  </>
                ) : (
                  <span className="pay-box-na">경력 표본 부족</span>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
