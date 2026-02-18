// 선택 스킬과 함께 요구되는 스택 (전국 동시출현 비율).
import type { RelatedSkillItem } from '../types'

interface Props {
  skill: string
  items: RelatedSkillItem[]
  loading: boolean
}

export default function SkillCooccur({ skill, items, loading }: Props) {
  if (!skill) return null
  const max = items.length ? items[0].lift : 1

  return (
    <section className="cooccur">
      <p className="cooccur-head">
        <strong>{skill}</strong> 와 함께 요구되는 스택
        <span className="cooccur-note"> · 연관도(lift)순</span>
      </p>
      {loading && <div className="cooccur-empty">불러오는 중…</div>}
      {!loading && items.length === 0 && (
        <div className="cooccur-empty">함께 잡히는 스택이 없습니다.</div>
      )}
      {!loading && items.length > 0 && (
        <ul className="cooccur-list">
          {items.map((it) => {
            const w = Math.max(3, (it.lift / max) * 100)
            return (
              <li key={it.skill} className="cooccur-row">
                <span className="cooccur-name">{it.skill}</span>
                <span className="cooccur-pct">×{it.lift} · {it.pct}%</span>
                <span className="cooccur-bar" style={{ width: `${w}%` }} />
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
