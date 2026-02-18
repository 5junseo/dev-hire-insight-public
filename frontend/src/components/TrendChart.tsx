// 공고 게시 추이 — 게시일(posted_at) 기준 주별 공고 수.
// 1개: 막대(주별) + 4주 이동평균 선. 2개 이상: 스킬별 멀티라인 비교(지수/건수).
// 무거운 차트 라이브러리 없이 d3-scale + 순수 SVG. /api/trend 을 스킬별로 병렬 호출.
import { useEffect, useMemo, useState } from 'react'
import { scaleBand, scaleLinear } from 'd3-scale'
import { fetchTrend } from '../api'
import type { SkillItem, TrendItem, Career } from '../types'
import { ALL_SKILL as ALL, skillLabel as labelOf } from '../types'

interface Props {
  skill: string
  career: Career
  skills: SkillItem[]
}

// viewBox 내부 좌표(렌더 크기와 무관). CSS 로 width:100% 스케일.
const W = 720
const H = 240
const PAD = { t: 16, r: 16, b: 28, l: 40 }

const MA_WIN = 4   // 이동평균 창(주)
const MAX = 4      // 동시 비교 스킬 수(기준 포함)
// 기준=핑크(테마색), 이후 파랑·초록·주황(지도 앰버와 구분되는 색상들).
const PALETTE = ['#e05a86', '#3b82c4', '#2f9e6b', '#c9792b']

// 전체 공고(스킬 무관) 추이 = 시장 기준선. 기준/비교 어느 쪽으로도 쓸 수 있다.
const ALL_COLOR = '#8a94a6'

const pad2 = (n: number) => String(n).padStart(2, '0')
const fmt = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`

// min~max 사이의 주(월요일) 시퀀스. 한국은 서머타임 없어 7일=고정 ms 로 안전.
function weekSequence(min: string, max: string): string[] {
  const out: string[] = []
  let t = new Date(min + 'T00:00:00').getTime()
  const end = new Date(max + 'T00:00:00').getTime()
  while (t <= end) {
    out.push(fmt(new Date(t)))
    t += 7 * 86400 * 1000
  }
  return out
}

interface Pt { cx: number; y: number; raw: number }
interface Series { skill: string; color: string; path: string; pts: Pt[]; peak: number; dashed: boolean }

export default function TrendChart({ skill, career, skills }: Props) {
  const [compare, setCompare] = useState<string[]>([])
  const [mode, setMode] = useState<'index' | 'abs'>('index')
  const [data, setData] = useState<Record<string, TrendItem[]>>({})
  const [loading, setLoading] = useState(false)
  const [hover, setHover] = useState<{ idx: number; px: number } | null>(null)

  // 기준 스킬을 새로 고르면 비교목록에서 제거(중복 방지).
  useEffect(() => { setCompare((c) => c.filter((s) => s !== skill)) }, [skill])

  // 표시 대상: 기준 + 비교(중복 제거, 최대 MAX개).
  const active = useMemo(() => {
    const seen = new Set<string>()
    const out: string[] = []
    for (const s of [skill, ...compare]) {
      if (s && !seen.has(s)) { seen.add(s); out.push(s) }
    }
    return out.slice(0, MAX)
  }, [skill, compare])

  const activeKey = active.join('|')

  // 활성 스킬들의 추이를 병렬 조회. 스킬/경력/구성 바뀌면 재조회.
  useEffect(() => {
    if (!active.length) { setData({}); return }
    let ignore = false
    setLoading(true)
    Promise.all(
      active.map((s) =>
        fetchTrend(s === ALL ? undefined : s, career)
          .then((items) => [s, items] as const)
          .catch(() => [s, [] as TrendItem[]] as const),
      ),
    )
      .then((pairs) => { if (!ignore) setData(Object.fromEntries(pairs)) })
      .finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [activeKey, career])

  const solo = active.length === 1
  const effMode: 'index' | 'abs' = solo ? 'abs' : mode

  const model = useMemo(() => {
    const allPeriods = active.flatMap((s) => (data[s] ?? []).map((i) => i.period))
    if (allPeriods.length < 2) return null
    const min = allPeriods.reduce((a, b) => (a < b ? a : b))
    const max = allPeriods.reduce((a, b) => (a > b ? a : b))
    const master = weekSequence(min, max)
    if (master.length < 2) return null

    const xb = scaleBand<string>().domain(master).range([PAD.l, W - PAD.r]).padding(0.28)
    const bw = xb.bandwidth()
    const cx = (p: string) => (xb(p) ?? 0) + bw / 2

    // 스킬별: 주축에 정렬(없는 주는 0) → 4주 이동평균 → (지수면 자기 피크=100 정규화).
    const prepared = active.map((s, si) => {
      const m = new Map((data[s] ?? []).map((i) => [i.period, i.cnt]))
      const raw = master.map((p) => m.get(p) ?? 0)
      const ma = raw.map((_, i) => {
        const win = raw.slice(Math.max(0, i - MA_WIN + 1), i + 1)
        return win.reduce((a, b) => a + b, 0) / win.length
      })
      const peakMa = Math.max(...ma, 1e-9)
      const plot = ma.map((v) => (effMode === 'index' ? (v / peakMa) * 100 : v))
      const color = s === ALL ? ALL_COLOR : PALETTE[si % PALETTE.length]
      return { skill: s, color, raw, ma, plot, dashed: s === ALL }
    })

    const yMax = effMode === 'index' ? 100 : Math.max(...prepared.flatMap((p) => p.plot), 1)
    const y = scaleLinear().domain([0, yMax]).nice().range([H - PAD.b, PAD.t])

    const series: Series[] = prepared.map((p) => {
      const pts = p.plot.map((v, i) => ({ cx: cx(master[i]), y: y(v), raw: p.raw[i] }))
      const path = pts.map((pt, i) => `${i ? 'L' : 'M'}${pt.cx.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ')
      return { skill: p.skill, color: p.color, path, pts, peak: Math.max(...p.raw, 0), dashed: p.dashed }
    })

    // 1개일 때만: 원자료 막대 + 이동평균 선(기존 UX 유지).
    const bars = solo
      ? prepared[0].raw.map((cnt, i) => {
          const yt = y(cnt)
          return { period: master[i], cnt, x: xb(master[i]) ?? 0, w: bw, y: yt, h: H - PAD.b - yt, cx: cx(master[i]), ma: prepared[0].ma[i] }
        })
      : []
    const maPathSolo = solo
      ? prepared[0].ma.map((v, i) => `${i ? 'L' : 'M'}${cx(master[i]).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
      : ''

    // x축 월 눈금 — 월이 바뀌는 주에 라벨.
    const xTicks: { x: number; label: string }[] = []
    let prevM = -1
    for (const p of master) {
      const d = new Date(p + 'T00:00:00')
      const mo = d.getMonth()
      if (mo !== prevM) {
        xTicks.push({ x: cx(p), label: mo === 0 ? `${d.getFullYear() % 100}.01` : `${mo + 1}월` })
        prevM = mo
      }
    }
    const yTicks = y.ticks(4).map((v) => ({ v, y: y(v) }))
    const cols = master.map((p) => ({ period: p, cx: cx(p) }))
    return { master, cols, series, bars, maPathSolo, xTicks, yTicks, baseY: H - PAD.b }
  }, [active, data, effMode, solo])

  if (!skill) return null

  const addCompare = (s: string) => {
    if (!s) return
    setCompare((c) => (c.includes(s) || active.length >= MAX ? c : [...c, s]))
  }
  const removeCompare = (s: string) => setCompare((c) => c.filter((x) => x !== s))

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!model) return
    const rect = e.currentTarget.getBoundingClientRect()
    const vx = ((e.clientX - rect.left) / rect.width) * W
    let best = 0
    for (let i = 1; i < model.cols.length; i++) {
      if (Math.abs(model.cols[i].cx - vx) < Math.abs(model.cols[best].cx - vx)) best = i
    }
    setHover({ idx: best, px: (model.cols[best].cx / W) * rect.width })
  }

  const opts = skills.filter((sk) => !active.includes(sk.skill)).slice(0, 300)

  return (
    <section className="trend">
      <p className="trend-head">
        {solo ? <><strong>{labelOf(skill)}</strong> 공고 게시 추이</> : <strong>공고 게시 추이 비교</strong>}
        <span className="trend-note">
          {solo
            ? ' · 막대=주별 · 선=4주 이동평균 · 게시일 기준'
            : effMode === 'index'
              ? ' · 선=4주 이동평균 · 지수(각 스킬 피크=100)'
              : ' · 선=4주 이동평균 · 실제 건수'}
        </span>
      </p>

      {/* 범례 + 비교 스킬 추가 + 모드 토글 */}
      <div className="trend-legend">
        {active.map((s, i) => (
          <span key={s} className="trend-chip">
            <i className="trend-swatch" style={{ background: s === ALL ? ALL_COLOR : PALETTE[i % PALETTE.length] }} />
            {labelOf(s)}
            {i === 0
              ? <em className="trend-base">기준</em>
              : <button type="button" className="trend-x" onClick={() => removeCompare(s)} aria-label={`${labelOf(s)} 비교 제거`}>×</button>}
          </span>
        ))}
        {active.length < MAX && (
          <select className="trend-add" value="" onChange={(e) => addCompare(e.target.value)}>
            <option value="">+ 비교 추가</option>
            {!active.includes(ALL) && <option value={ALL}>전체 공고(시장 기준)</option>}
            {opts.map((sk) => <option key={sk.skill} value={sk.skill}>{sk.skill}</option>)}
          </select>
        )}
        {active.length >= 2 && (
          <div className="trend-mode" role="group" aria-label="표시 방식">
            <button type="button" className={effMode === 'index' ? 'on' : ''} onClick={() => setMode('index')}>지수</button>
            <button type="button" className={effMode === 'abs' ? 'on' : ''} onClick={() => setMode('abs')}>건수</button>
          </div>
        )}
      </div>

      {loading && <div className="trend-empty">불러오는 중…</div>}
      {!loading && !model && <div className="trend-empty">추이를 그릴 데이터가 아직 부족합니다.</div>}

      {!loading && model && (
        <div className="trend-wrap">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="trend-svg"
            role="img"
            aria-label={solo ? `${labelOf(skill)} 주별 공고 게시 추이` : '스킬별 주별 공고 게시 추이 비교'}
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
          >
            {/* y 그리드 + 눈금 */}
            {model.yTicks.map((t) => (
              <g key={`y${t.v}`}>
                <line x1={PAD.l} x2={W - PAD.r} y1={t.y} y2={t.y} className="trend-grid" />
                <text x={PAD.l - 6} y={t.y + 3} className="trend-axis" textAnchor="end">{t.v}</text>
              </g>
            ))}

            {/* 호버 세로선(비교 모드) */}
            {!solo && hover && (
              <line
                x1={model.cols[hover.idx].cx} x2={model.cols[hover.idx].cx}
                y1={PAD.t} y2={model.baseY} className="trend-guide"
              />
            )}

            {/* 1개: 막대 + 이동평균 */}
            {solo && model.bars.map((b) => (
              <rect
                key={b.period}
                x={b.x} y={b.y} width={b.w} height={Math.max(0, b.h)}
                rx={Math.min(2.5, b.w / 2)}
                className="trend-bar"
                style={{ opacity: hover ? (hover.idx === model.bars.indexOf(b) ? 1 : 0.45) : 0.9 }}
              />
            ))}
            {solo && <path d={model.maPathSolo} className="trend-ma" />}

            {/* 여러 개: 스킬별 라인 */}
            {!solo && model.series.map((s) => (
              <path key={s.skill} d={s.path} className="trend-line" style={{ stroke: s.color, strokeDasharray: s.dashed ? '5 4' : undefined }} />
            ))}
            {/* 여러 개: 호버 지점 마커 */}
            {!solo && hover && model.series.map((s) => (
              <circle key={s.skill} cx={s.pts[hover.idx].cx} cy={s.pts[hover.idx].y} r={3} className="trend-dot" style={{ fill: s.color }} />
            ))}

            {/* 바닥선 */}
            <line x1={PAD.l} x2={W - PAD.r} y1={model.baseY} y2={model.baseY} className="trend-baseline" />

            {/* x 눈금(월) */}
            {model.xTicks.map((t, i) => (
              <text key={`x${i}`} x={t.x} y={model.baseY + 18} className="trend-axis" textAnchor="middle">{t.label}</text>
            ))}
          </svg>

          {hover && solo && (
            <div className="trend-tip" style={{ left: hover.px, top: (model.bars[hover.idx].y / H) * 100 + '%' }}>
              <strong>{model.bars[hover.idx].cnt.toLocaleString()}건</strong>
              <span className="trend-tip-ma">4주평균 {model.bars[hover.idx].ma.toFixed(1)}</span>
              <span className="trend-tip-date">{model.bars[hover.idx].period} 주</span>
            </div>
          )}
          {hover && !solo && (
            <div className="trend-tip trend-tip-multi" style={{ left: hover.px, top: 0 }}>
              <span className="trend-tip-date">{model.cols[hover.idx].period} 주</span>
              {model.series
                .map((s) => ({ skill: s.skill, color: s.color, raw: s.pts[hover.idx].raw }))
                .sort((a, b) => b.raw - a.raw)
                .map((r) => (
                  <span key={r.skill} className="trend-tip-row">
                    <i className="trend-swatch" style={{ background: r.color }} />
                    {labelOf(r.skill)} <b>{r.raw.toLocaleString()}건</b>
                  </span>
                ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
