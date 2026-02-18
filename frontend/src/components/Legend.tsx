// 공고 수 색상 범례 (0 ~ max건).
import { useMemo } from 'react'

interface Props {
  max: number
  interpolate: (t: number) => string
  emptyColor: string
}

export default function Legend({ max, interpolate, emptyColor }: Props) {
  const gradient = useMemo(() => {
    const stops = Array.from({ length: 8 }, (_, i) => {
      const t = i / 7
      return `${interpolate(t)} ${Math.round(t * 100)}%`
    })
    return `linear-gradient(to right, ${stops.join(', ')})`
  }, [interpolate])

  return (
    <div className="legend">
      <span className="legend-title">공고 수</span>
      <div className="legend-scale">
        <span className="legend-min">0</span>
        <span className="legend-bar" style={{ background: gradient }} />
        <span className="legend-max">{Math.round(max).toLocaleString()}</span>
      </div>
      <span className="legend-empty">
        <span className="legend-swatch" style={{ background: emptyColor }} /> 공고 없음
      </span>
    </div>
  )
}
