// 경력밴드 세그먼트 토글 (all / junior / senior).
import type { Career } from '../types'

const OPTS: { value: Career; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'junior', label: '주니어 0-2년' },
  { value: 'senior', label: '시니어 3년+' },
]

interface Props {
  value: Career
  onChange: (c: Career) => void
}

export default function CareerToggle({ value, onChange }: Props) {
  return (
    <div className="career-toggle" role="group" aria-label="경력 밴드">
      <span className="ctrl-label">경력</span>
      <div className="seg">
        {OPTS.map((o) => (
          <button
            key={o.value}
            type="button"
            className={o.value === value ? 'seg-btn on' : 'seg-btn'}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}
