import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import type { TelemetryReading } from '../hooks/useTelemetry'
import { fmt, niceStep, phaseLabel, phaseSpans } from '../flight'
import { xScale } from '../chartScale'
import type { Band } from '../chartScale'
import StripChart from './StripChart'

const STRIPS: {
  title: string; unit: string; short: string; digits: number; height: number
  minSpan: number; fromZero?: boolean
  value: (r: TelemetryReading) => number | null
}[] = [
  // A wide minimum range keeps sensor noise on the pad looking like a flat line
  { title: 'Altitude', unit: 'm above pad', short: 'm', digits: 1, height: 250, minSpan: 100,
    fromZero: true,
    value: r => r.altitude_m },
  { title: 'Acceleration', unit: 'm/s², along the rocket', short: 'm/s²', digits: 2, height: 120,
    minSpan: 20,
    value: r => r.imu_accel_z },
  { title: 'Pressure', unit: 'hPa', short: 'hPa', digits: 1, height: 120, minSpan: 5,
    value: r => r.pressure_hpa },
  { title: 'Temperature', unit: '°C', short: '°C', digits: 1, height: 120, minSpan: 5,
    value: r => r.temperature_c },
]

const PAD_WINDOW_S = 60     // how much pad time to show while waiting
const BEFORE_LAUNCH_S = 5   // how much pad time to keep once the flight starts
const TABLE_ROWS = 12

/** The flight's measurements as stacked strips on one shared time axis. */
export default function FlightCharts({ flight, times, launched, hoverIndex, onHover }: {
  flight: TelemetryReading[]
  times: number[]   // seconds from launch, or seconds before now while on the pad
  launched: boolean
  hoverIndex: number | null
  onHover: (time: number | null) => void
}) {
  const frame = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(800)

  useEffect(() => {
    const element = frame.current
    if (!element) return
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const latest = times.length ? times[times.length - 1] : 0
  const zero = flight.length ? flight[flight.length - 1].timestamp - latest * 1000 : 0
  const seconds = (timestamp: number) => (timestamp - zero) / 1000

  let domain: [number, number]
  let step: number
  if (launched) {
    step = niceStep(Math.max(latest, 30) + BEFORE_LAUNCH_S, 8)
    domain = [-BEFORE_LAUNCH_S, Math.max(Math.ceil((latest + 1) / step) * step, 30)]
  } else {
    step = 10
    domain = [-PAD_WINDOW_S, 0]
  }
  const xTicks: number[] = []
  for (let t = Math.ceil(domain[0] / step) * step; t <= domain[1]; t += step) xTicks.push(t)

  const bands: Band[] = launched
    ? phaseSpans(flight).map(span => ({
        label: phaseLabel(span.phase), from: seconds(span.from), to: seconds(span.to),
      }))
    : []
  // The band in progress runs to the right-hand edge of the newest reading
  if (bands.length) bands[bands.length - 1].to = latest

  const hovered = hoverIndex != null ? flight[hoverIndex] : null

  const onKey = (event: KeyboardEvent) => {
    if (!times.length) return
    if (event.key === 'Escape') return onHover(null)
    const move = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0
    if (move === 0) return
    event.preventDefault()
    const from = hoverIndex ?? times.length - 1
    const to = Math.min(Math.max(from + move * (event.shiftKey ? 10 : 1), 0), times.length - 1)
    onHover(times[to])
  }

  const clock = (t: number) => launched
    ? `T${t < 0 ? '−' : '+'}${Math.abs(t).toFixed(1)} s`
    : `${Math.abs(t).toFixed(1)} s ago`

  // Keep the tooltip inside the frame by flipping it to the left of the line
  const hoverX = hoverIndex != null ? xScale(width, domain)(times[hoverIndex]) : 0
  const tooltipStyle = hoverX > width - 230 ? { right: width - hoverX + 12 } : { left: hoverX + 12 }

  return (
    <section>
      <h2>Flight data <span>{launched ? 'seconds from launch' : 'waiting on the pad'}</span></h2>
      <div className="charts" ref={frame} tabIndex={0} onKeyDown={onKey}
        aria-label="Flight data charts. Use the left and right arrow keys to read values.">
        {STRIPS.map((strip, i) => (
          <StripChart key={strip.title} title={strip.title} unit={strip.unit}
            times={times} values={flight.map(strip.value)} domain={domain} xTicks={xTicks}
            width={width} height={strip.height} minSpan={strip.minSpan}
            fromZero={strip.fromZero} bands={bands}
            showBandLabels={i === 0} showXAxis={i === STRIPS.length - 1}
            xAxisLabel={launched ? 'seconds from launch' : 'seconds before now'}
            hoverIndex={hoverIndex} onHover={onHover} />
        ))}

        {hovered && hoverIndex != null && (
          <div className="tooltip" style={tooltipStyle}>
            <div className="when">
              {clock(times[hoverIndex])}{hovered.phase && ` · ${phaseLabel(hovered.phase)}`}
            </div>
            {STRIPS.map(strip => (
              <div className="row" key={strip.title}>
                <span className="key" />
                <span className="v">{fmt(strip.value(hovered), strip.digits)}</span>
                <span className="u">{strip.short}</span>
                <span className="l">{strip.title}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <details>
        <summary>Latest readings as a table</summary>
        <table className="log">
          <thead>
            <tr>
              <th>Time</th><th>Phase</th>
              {STRIPS.map(s => <th className="num" key={s.title}>{s.title}</th>)}
            </tr>
          </thead>
          <tbody>
            {flight.slice(-TABLE_ROWS).reverse().map(r => (
              <tr key={r.timestamp}>
                <td>{clock(seconds(r.timestamp))}</td>
                <td>{phaseLabel(r.phase)}</td>
                {STRIPS.map(s => <td className="num" key={s.title}>{fmt(s.value(r), s.digits)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  )
}
