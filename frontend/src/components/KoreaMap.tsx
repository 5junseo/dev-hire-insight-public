// 시도 코로플레스 지도 — react-simple-maps 없이 d3-geo 로 직접 SVG path 렌더.
// props 로 받은 밀도값에 색을 입히고, 지역 클릭/hover 를 상위로 올린다.
import { useMemo, useState } from 'react'
import { geoMercator, geoPath } from 'd3-geo'
import type { FeatureCollection, Geometry } from 'geojson'
import sidoGeoRaw from '../data/korea-sido.json'

const sidoGeo = sidoGeoRaw as unknown as FeatureCollection<Geometry, { sido: string; name: string }>

const W = 520
const H = 640

export interface MapDatum {
  count: number
  density: number
}

interface Props {
  /** sido(짧은 이름) -> {count, density} */
  data: Map<string, MapDatum>
  /** sido -> 채움색 */
  colorFor: (sido: string) => string
  selectedSido: string | null
  onSelect: (sido: string) => void
}

export default function KoreaMap({ data, colorFor, selectedSido, onSelect }: Props) {
  const [hover, setHover] = useState<{ sido: string; x: number; y: number } | null>(null)

  // 투영은 geojson 에 맞춰 한 번만 계산 (fitSize 로 뷰박스 꽉 채움).
  const path = useMemo(() => {
    const projection = geoMercator().fitSize([W, H], sidoGeo)
    return geoPath(projection)
  }, [])

  return (
    <div className="map-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="map-svg" role="img" aria-label="시도별 공고 수 지도">
        <g>
          {sidoGeo.features.map((f) => {
            const sido = f.properties.sido
            const d = path(f) ?? undefined
            const isSel = sido === selectedSido
            return (
              <path
                key={sido}
                d={d}
                fill={colorFor(sido)}
                stroke={isSel ? '#1f2937' : '#ffffff'}
                strokeWidth={isSel ? 2 : 0.7}
                className="sido-path"
                onClick={() => onSelect(sido)}
                onMouseMove={(e) => {
                  const rect = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
                  setHover({ sido, x: e.clientX - rect.left, y: e.clientY - rect.top })
                }}
                onMouseLeave={() => setHover((h) => (h?.sido === sido ? null : h))}
              />
            )
          })}
        </g>
      </svg>

      {hover && (
        <div className="map-tip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
          <strong>{hover.sido}</strong>
          {(() => {
            const d = data.get(hover.sido)
            if (!d) return <div className="tip-muted">데이터 없음</div>
            return <div>공고 {d.count.toLocaleString()}건</div>
          })()}
        </div>
      )}
    </div>
  )
}
