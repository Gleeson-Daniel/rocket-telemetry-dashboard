import type { FlightSummary, TelemetryReading } from '../hooks/useTelemetry'
import { PHASES, fmt, phaseLabel, phaseSpans } from '../flight'

function Figure({ label, value, unit, hero = false }: {
  label: string; value: string; unit?: string; hero?: boolean
}) {
  return (
    <div className={hero ? 'figure hero' : 'figure'}>
      <div className="label">{label}</div>
      <div className="value">{value}{unit && <span className="unit">{unit}</span>}</div>
    </div>
  )
}

/** The numbers you look at first, and where the flight is in its sequence. */
export default function Headline({ flight, launchedAt, summary }: {
  flight: TelemetryReading[]
  launchedAt: number | null
  summary: FlightSummary | null
}) {
  const latest = flight[flight.length - 1]
  const current = latest?.phase
  const currentIndex = PHASES.findIndex(p => p.id === current)

  // When each phase was first entered, in seconds from launch
  const entered = new Map<string, number>()
  if (launchedAt != null) {
    for (const span of phaseSpans(flight)) {
      if (!entered.has(span.phase)) entered.set(span.phase, (span.from - launchedAt) / 1000)
    }
  }

  return (
    <section>
      <div className="headline">
        <Figure hero label="Altitude above pad" value={fmt(latest?.altitude_m, 1)} unit="m" />
        <Figure label="Flight time" unit="s"
          value={launchedAt != null && summary ? `T+${summary.flight_time_s.toFixed(1)}` : 'T+0.0'} />
        <Figure label="Phase" value={phaseLabel(current)} />
        <Figure label="Peak altitude" unit="m" value={fmt(summary?.peak_altitude_m, 1)} />
        <Figure label="Peak acceleration" unit="m/s²" value={fmt(summary?.max_accel_ms2, 1)} />
      </div>

      <div className="phases">
        {PHASES.map((phase, i) => {
          const state = i === currentIndex ? 'phase reached current'
            : i < currentIndex ? 'phase reached' : 'phase'
          const time = entered.get(phase.id)
          return (
            <div className={state} key={phase.id}
              aria-current={i === currentIndex ? 'step' : undefined}>
              <div className="name">{phase.label}</div>
              <div className="when">
                {phase.id === 'PAD' || time == null ? ' ' : `T+${time.toFixed(1)} s`}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
