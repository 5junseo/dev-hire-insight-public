// "내 스킬" 프로필 카드 — 스킬 칩 입력 + 맞춤 결과(추천 스택 / 수요 지역).
// 데이터 계산은 App 이 하고(기존 /api/cooccur·/api/map 재활용), 여기선 표시/입력만.
import { useState } from 'react'
import type { SkillItem } from '../types'

export interface RecItem {
  skill: string
  score: number   // 내 스킬들과의 동시출현 pct 합
  matches: number // 내 스킬 중 몇 개와 함께 잡히나
}
export interface DemandItem {
  sido: string
  count: number   // 내 스킬 공고 수 합(시도별)
}

interface Props {
  skills: SkillItem[]
  profile: string[]
  onAdd: (skill: string) => void
  onRemove: (skill: string) => void
  rec: RecItem[]
  demand: DemandItem[]
  loading: boolean
  onPickSkill: (skill: string) => void
  onPickRegion: (sido: string) => void
}

export default function ProfileCard({
  skills, profile, onAdd, onRemove, rec, demand, loading, onPickSkill, onPickRegion,
}: Props) {
  const [draft, setDraft] = useState('')

  const submit = () => {
    const v = draft.trim().toLowerCase()
    if (!v) return
    // 카탈로그에 있는 스킬만 추가(추천/집계가 성립하도록)
    const hit = skills.find((s) => s.skill.toLowerCase() === v)
    if (hit && !profile.includes(hit.skill)) onAdd(hit.skill)
    setDraft('')
  }

  const recMax = rec.length ? rec[0].score : 1
  const demandMax = demand.length ? demand[0].count : 1

  return (
    <section className="profile">
      <div className="profile-head">
        <h2>내 스킬</h2>
        <span className="profile-hint">보유 스택을 추가하면 맞춤 추천과 수요 지역을 보여줘요</span>
      </div>

      <div className="chips">
        {profile.map((s) => (
          <span key={s} className="chip">
            {s}
            <button type="button" className="chip-x" onClick={() => onRemove(s)} aria-label={`${s} 제거`}>
              ×
            </button>
          </span>
        ))}
        <span className="chip-add">
          <input
            list="skill-catalog"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submit() } }}
            placeholder="스킬 입력 (예: python)"
          />
          <button type="button" onClick={submit}>추가</button>
          <datalist id="skill-catalog">
            {skills.map((s) => <option key={s.skill} value={s.skill} />)}
          </datalist>
        </span>
      </div>

      {profile.length === 0 ? (
        <p className="profile-empty">아직 추가한 스킬이 없어요. 위에서 보유 스택을 골라보세요.</p>
      ) : (
        <div className="profile-results">
          <div className="profile-block">
            <p className="profile-block-head">다음에 배우면 좋은 스택</p>
            {loading && <div className="profile-block-empty">계산 중…</div>}
            {!loading && rec.length === 0 && <div className="profile-block-empty">추천할 스택이 없어요.</div>}
            {!loading && rec.length > 0 && (
              <ul className="rec-list">
                {rec.map((r) => (
                  <li key={r.skill} className="rec-row">
                    <button type="button" className="rec-btn" onClick={() => onPickSkill(r.skill)}>
                      <span className="rec-name">{r.skill}</span>
                      <span className="rec-meta">{r.matches}개 스택과 함께</span>
                      <span className="rec-bar" style={{ width: `${Math.max(4, (r.score / recMax) * 100)}%` }} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="profile-block">
            <p className="profile-block-head">내 스택 수요 TOP 지역</p>
            {loading && <div className="profile-block-empty">계산 중…</div>}
            {!loading && demand.length === 0 && <div className="profile-block-empty">데이터가 없어요.</div>}
            {!loading && demand.length > 0 && (
              <ul className="rec-list">
                {demand.map((d) => (
                  <li key={d.sido} className="rec-row">
                    <button type="button" className="rec-btn" onClick={() => onPickRegion(d.sido)}>
                      <span className="rec-name">{d.sido}</span>
                      <span className="rec-meta">{d.count.toLocaleString()}건</span>
                      <span className="rec-bar" style={{ width: `${Math.max(4, (d.count / demandMax) * 100)}%` }} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
