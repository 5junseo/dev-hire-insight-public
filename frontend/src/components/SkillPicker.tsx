// 스킬 드롭다운 — 전국 순위/공고수를 함께 보여준다. 맨 위 '전체'는 스킬 무관(전체 공고).
import type { SkillItem } from '../types'
import { ALL_SKILL } from '../types'

interface Props {
  skills: SkillItem[]
  value: string
  onChange: (skill: string) => void
}

export default function SkillPicker({ skills, value, onChange }: Props) {
  return (
    <label className="skill-picker">
      <span className="ctrl-label">스킬</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value={ALL_SKILL}>전체 공고</option>
        {skills.map((s) => (
          <option key={s.skill} value={s.skill}>
            {s.rank_no}. {s.skill} ({s.total_cnt.toLocaleString()})
          </option>
        ))}
      </select>
    </label>
  )
}
