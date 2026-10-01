import type { TrackPoint } from '../flight'
import { niceStep } from '../flight'

const SIZE = 300
const CENTER = SIZE / 2
const RADIUS = 126  // pixels from the pad to the edge of the plotted area
const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

/** Where the rocket has drifted, seen from above with the pad in the middle. */
export default function GroundTrack({ track, launchIndex, hoverIndex }: {
  track: (TrackPoint | null)[] | null
  launchIndex: number | null  // where in the track the flight left the pad
  hoverIndex: number | null
}) {
  // Only the flight itself is drawn; on the pad there is nowhere to go
  const flown = launchIndex != null ? (track ?? []).slice(launchIndex) : []
  const points = flown.filter((p): p is TrackPoint => p != null)
  const latest = track?.[track.length - 1] ?? null

  // Scale so the furthest point fits, on a round number of metres
  const reach = Math.max(20, ...points.map(p => Math.hypot(p.east, p.north)))
  const ring = niceStep(reach, 2)
  const extent = Math.ceil(reach / ring) * ring
  const px = (p: TrackPoint) => ({
    x: CENTER + p.east / extent * RADIUS,
    y: CENTER - p.north / extent * RADIUS,
  })

  const stride = Math.ceil(points.length / 400) || 1
  const path = points
    .filter((_, i) => i % stride === 0 || i === points.length - 1)
    .map((p, i) => `${i ? 'L' : 'M'}${px(p).x.toFixed(1)} ${px(p).y.toFixed(1)}`)
    .join('')

  const rings: number[] = []
  for (let r = ring; r <= extent; r += ring) rings.push(r)

  const hovered = hoverIndex != null ? track?.[hoverIndex] : null
  const marked = hovered ?? (launchIndex != null ? latest : null)
  const distance = latest ? Math.hypot(latest.east, latest.north) : 0
  const bearing = latest ? (Math.atan2(latest.east, latest.north) * 180 / Math.PI + 360) % 360 : 0

  return (
    <section className="track">
      <h2>Ground track <span>metres from the pad</span></h2>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img"
        aria-label="Map of the rocket's position relative to the launch pad">
        {rings.map(r => (
          <g key={r}>
            <circle className="gridline" cx={CENTER} cy={CENTER}
              r={r / extent * RADIUS} fill="none" />
            <text className="tick" x={CENTER + 4}
              y={CENTER - r / extent * RADIUS + 12}>{r} m</text>
          </g>
        ))}
        <line className="gridline" x1={CENTER} x2={CENTER} y1={12} y2={SIZE - 12} />
        <line className="gridline" x1={12} x2={SIZE - 12} y1={CENTER} y2={CENTER} />
        <text className="tick" x={CENTER} y={11} textAnchor="middle">N</text>
        <text className="tick" x={SIZE - 4} y={CENTER + 4} textAnchor="end">E</text>

        {track == null
          ? <text className="empty-note" x={CENTER} y={CENTER + 34}
              textAnchor="middle">No GPS in this log</text>
          : <path className="trace" d={path} />}

        {/* The pad */}
        <line className="pad-mark" x1={CENTER - 6} x2={CENTER + 6} y1={CENTER} y2={CENTER} />
        <line className="pad-mark" x1={CENTER} x2={CENTER} y1={CENTER - 6} y2={CENTER + 6} />

        {marked && <circle className="dot" cx={px(marked).x} cy={px(marked).y} r={5} />}
      </svg>
      <div className="caption">
        {track == null || !latest ? 'No position'
          : distance < 5 ? 'On the pad'
          : `${distance.toFixed(0)} m from the pad, to the ${COMPASS[Math.round(bearing / 45) % 8]} ` +
            `(${bearing.toFixed(0).padStart(3, '0')}°)`}
      </div>
    </section>
  )
}
