// 선택 지역의 인기 스택 순위(막대) + 선택 스킬의 시군구 분포(드릴다운).
import type { RegionSkillItem, SigunguItem } from '../types'
import { skillLabel } from '../types'

interface Props {
  sido: string | null
  items: RegionSkillItem[]
  loading: boolean
  activeSkill: string
  onPickSkill: (skill: string) => void
  drilldown: SigunguItem[]
  drilldownLoading: boolean
}

export default function RegionPanel({
  sido, items, loading, activeSkill, onPickSkill, drilldown, drilldownLoading,
}: Props) {
  if (!sido) {
    return (
      <aside className="panel">
        <div className="panel-empty">지도에서 지역을 클릭하면<br />그 지역의 인기 스택 순위가 나옵니다.</div>
      </aside>
    )
  }

  const max = items.length ? items[0].count : 1
  const drillMax = drilldown.length ? drilldown[0].count : 1

  return (
    <aside className="panel">
      <h2 className="panel-title">
        {sido} <span className="panel-sub">인기 스택</span>
      </h2>
      {loading && <div className="panel-empty">불러오는 중…</div>}
      {!loading && items.length === 0 && <div className="panel-empty">데이터가 없습니다.</div>}
      <ol className="rank-list">
        {items.map((it, i) => {
          const pct = Math.max(2, (it.count / max) * 100)
          const on = it.skill === activeSkill
          return (
            <li key={it.skill} className={on ? 'rank-row on' : 'rank-row'}>
              <button type="button" className="rank-btn" onClick={() => onPickSkill(it.skill)}>
                <span className="rank-no">{i + 1}</span>
                <span className="rank-name">{it.skill}</span>
                <span className="rank-count">{it.count.toLocaleString()}</span>
                <span className="rank-bar" style={{ width: `${pct}%` }} />
              </button>
            </li>
          )
        })}
      </ol>

      <section className="drill">
        <p className="drill-head">
          <strong>{skillLabel(activeSkill)}</strong> · {sido} 시군구 분포
        </p>
        {drilldownLoading && <div className="drill-empty">불러오는 중…</div>}
        {!drilldownLoading && drilldown.length === 0 && (
          <div className="drill-empty">시군구 단위 데이터가 없습니다.</div>
        )}
        {!drilldownLoading && drilldown.length > 0 && (
          <ul className="drill-list">
            {drilldown.map((d) => {
              const pct = Math.max(2, (d.count / drillMax) * 100)
              return (
                <li key={d.sigungu} className="drill-row">
                  <span className="drill-name">{d.sigungu}</span>
                  <span className="drill-count">{d.count.toLocaleString()}</span>
                  <span className="drill-bar" style={{ width: `${pct}%` }} />
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </aside>
  )
}
