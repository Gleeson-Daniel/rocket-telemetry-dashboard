import type { PointerEvent } from 'react'
import { niceStep } from '../flight'
import { MARGIN, xScale } from '../chartScale'
import type { Band } from '../chartScale'

const X_AXIS_HEIGHT = 34
const MAX_PATH_POINTS = 700

function tickLabel(value: number, step: number) {
  const digits = step >= 1 ? 0 : Math.ceil(-Math.log10(step))
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  })
}

/** One measurement against time. Strips are stacked so they share an x-axis. */
export default function StripChart({
  title, unit, times, values, domain, xTicks, width, height, minSpan, fromZero = false,
  bands, showBandLabels = false, showXAxis = false, xAxisLabel,
  hoverIndex, onHover,
}: {
  title: string
  unit: string
  times: number[]
  values: (number | null)[]
  domain: [number, number]
  xTicks: number[]
  width: number
  height: number
  minSpan: number  // smallest y-range to show, so noise at rest doesn't fill the plot
  fromZero?: boolean  // start the scale at zero, for a quantity that rests there
  bands: Band[]
  showBandLabels?: boolean
  showXAxis?: boolean
  xAxisLabel?: string
  hoverIndex: number | null
  onHover: (time: number | null) => void
}) {
  const total = height + (showXAxis ? X_AXIS_HEIGHT : 8)
  const plotBottom = height
  const plotHeight = height - MARGIN.top
  const x = xScale(width, domain)

  // Y scale: round tick values, and never tighter than minSpan
  const present = values.filter((v): v is number => v != null)
  let lo = present.length ? Math.min(...present) : 0
  let hi = present.length ? Math.max(...present) : 1
  let step: number
  if (fromZero) {
    // Noise takes a value resting at zero slightly negative. Give that one
    // step of room below zero when it shows, and none when it doesn't.
    hi = Math.max(hi, minSpan)
    step = niceStep(hi, height > 160 ? 4 : 3)
    lo = lo < -0.02 * hi ? -step : 0
  } else {
    if (hi - lo < minSpan) {
      const middle = (lo + hi) / 2
      lo = middle - minSpan / 2
      hi = middle + minSpan / 2
    }
    step = niceStep(hi - lo, height > 160 ? 5 : 3)
    lo = Math.floor(lo / step) * step
  }
  hi = Math.ceil(hi / step) * step
  const yTicks: number[] = []
  for (let v = lo; v <= hi + step / 2; v += step) yTicks.push(v)
  const y = (v: number) => plotBottom - (v - lo) / (hi - lo) * plotHeight

  // Thin the line out to at most MAX_PATH_POINTS, always keeping the newest
  const stride = Math.ceil(times.length / MAX_PATH_POINTS) || 1
  let path = ''
  let penDown = false
  for (let i = 0; i < times.length; i++) {
    if (i % stride !== 0 && i !== times.length - 1) continue
    const v = values[i]
    if (v == null || times[i] < domain[0]) { penDown = false; continue }
    path += `${penDown ? 'L' : 'M'}${x(times[i]).toFixed(1)} ${y(v).toFixed(1)}`
    penDown = true
  }

  const last = times.length - 1
  const lastValue = last >= 0 ? values[last] : null
  const hoverValue = hoverIndex != null ? values[hoverIndex] : null

  const track = (event: PointerEvent<SVGRectElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const fraction = (event.clientX - box.left) / box.width
    onHover(domain[0] + fraction * (domain[1] - domain[0]))
  }

  return (
    <svg width={width} height={total} role="img" aria-label={`${title} over time`}>
      {bands.map((band, i) => {
        const from = Math.max(x(band.from), MARGIN.left)
        const to = Math.min(x(band.to), width - MARGIN.right)
        if (to <= from) return null
        // Roughly 6.2px per character at this size; skip a label that won't fit
        const fits = to - from > band.label.length * 6.2 + 10
        return (
          <g key={`${band.label}-${band.from}`}>
            {i % 2 === 1 && <rect className="band" x={from} y={MARGIN.top}
              width={to - from} height={plotHeight} />}
            {i > 0 && <line className="axisline" x1={from} x2={from}
              y1={MARGIN.top} y2={plotBottom} />}
            {showBandLabels && fits && <text className="band-label" x={from + 5}
              y={MARGIN.top + 13}>{band.label}</text>}
          </g>
        )
      })}

      {yTicks.map(v => (
        <g key={v}>
          <line className="gridline" x1={MARGIN.left} x2={width - MARGIN.right}
            y1={y(v)} y2={y(v)} />
          <text className="tick" x={MARGIN.left - 8} y={y(v) + 4}
            textAnchor="end">{tickLabel(v, step)}</text>
        </g>
      ))}
      <line className="axisline" x1={MARGIN.left} x2={width - MARGIN.right}
        y1={plotBottom} y2={plotBottom} />

      <text className="chart-title" x={MARGIN.left} y={15}>
        {title} <tspan>{unit}</tspan>
      </text>

      {showXAxis && xTicks.map(t => (
        <text key={t} className="tick" x={x(t)} y={plotBottom + 16}
          textAnchor="middle">{t}</text>
      ))}
      {showXAxis && xAxisLabel && <text className="tick" x={width - MARGIN.right}
        y={plotBottom + 31} textAnchor="end">{xAxisLabel}</text>}

      {present.length === 0
        ? <text className="empty-note" x={MARGIN.left + 8}
            y={MARGIN.top + plotHeight / 2 + 4}>Not recorded in this log</text>
        : <path className="trace" d={path} />}

      {lastValue != null && times[last] >= domain[0] &&
        <circle className="dot" cx={x(times[last])} cy={y(lastValue)} r={4} />}

      {hoverIndex != null && <line className="crosshair" x1={x(times[hoverIndex])}
        x2={x(times[hoverIndex])} y1={MARGIN.top} y2={plotBottom} />}
      {hoverIndex != null && hoverValue != null && <circle className="dot"
        cx={x(times[hoverIndex])} cy={y(hoverValue)} r={4} />}

      {/* Hover target: the whole plot, so the pointer only has to be near */}
      <rect x={MARGIN.left} y={MARGIN.top} width={Math.max(width - MARGIN.left - MARGIN.right, 1)}
        height={plotHeight} fill="transparent"
        onPointerMove={track} onPointerLeave={() => onHover(null)} />
    </svg>
  )
}
