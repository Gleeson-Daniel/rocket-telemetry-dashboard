// Pure helpers that turn the stream of readings into what the page displays.
import type { FlightPhase, TelemetryReading } from './hooks/useTelemetry'

export const PHASES: { id: FlightPhase; label: string }[] = [
  { id: 'PAD', label: 'Pad' },
  { id: 'POWERED_ASCENT', label: 'Powered ascent' },
  { id: 'COAST', label: 'Coast' },
  { id: 'APOGEE', label: 'Apogee' },
  { id: 'DESCENT', label: 'Descent' },
  { id: 'LANDED', label: 'Landed' },
]

export const phaseLabel = (phase: FlightPhase | undefined) =>
  PHASES.find(p => p.id === phase)?.label ?? '–'

// The ground station gives replayed logs flight id 0
export const flightName = (id: number | undefined) =>
  id == null ? '' : id === 0 ? 'Replay' : `Flight ${id}`

export const fmt = (value: number | null | undefined, digits: number) =>
  value == null ? '–' : value.toFixed(digits)

/** The readings at the end of the buffer that belong to the newest flight. */
export function currentFlight(readings: TelemetryReading[]): TelemetryReading[] {
  if (readings.length === 0) return readings
  const id = readings[readings.length - 1].flight_id
  let start = readings.length - 1
  while (start > 0 && readings[start - 1].flight_id === id) start--
  return readings.slice(start)
}

/** When the flight left the pad, or null if it hasn't. */
export function launchTimestamp(flight: TelemetryReading[]): number | null {
  const first = flight.find(r => r.phase != null && r.phase !== 'PAD')
  return first ? first.timestamp : null
}

export interface PhaseSpan { phase: FlightPhase; from: number; to: number }

/** Each stretch of the flight spent in one phase, as timestamps. */
export function phaseSpans(flight: TelemetryReading[]): PhaseSpan[] {
  const spans: PhaseSpan[] = []
  for (const r of flight) {
    if (r.phase == null) continue
    const last = spans[spans.length - 1]
    if (last && last.phase === r.phase) last.to = r.timestamp
    else {
      if (last) last.to = r.timestamp
      spans.push({ phase: r.phase, from: r.timestamp, to: r.timestamp })
    }
  }
  return spans
}

/** Climb rate in m/s from the last second of altitude readings. */
export function verticalSpeed(flight: TelemetryReading[]): number | null {
  if (flight.length < 10) return null
  const mean = (rows: TelemetryReading[]) =>
    rows.reduce((sum, r) => sum + r.altitude_m, 0) / rows.length
  const recent = flight.slice(-5)
  const earlier = flight.slice(-10, -5)
  const seconds = (recent[2].timestamp - earlier[2].timestamp) / 1000
  return seconds > 0 ? (mean(recent) - mean(earlier)) / seconds : null
}

export interface TrackPoint { east: number; north: number }

const METERS_PER_DEGREE = 111320

const GPS_SMOOTHING = 15  // readings averaged per position, to calm GPS jitter

/** GPS positions as metres east and north of where the flight began; null without GPS. */
export function groundTrack(flight: TelemetryReading[]): (TrackPoint | null)[] | null {
  const fixes = flight.filter(r => r.gps_lat != null && r.gps_lon != null)
  if (fixes.length === 0) return null
  // The pad is the average of the first fixes, since any single one is noisy
  const first = fixes.slice(0, GPS_SMOOTHING)
  const lat0 = first.reduce((sum, r) => sum + r.gps_lat!, 0) / first.length
  const lon0 = first.reduce((sum, r) => sum + r.gps_lon!, 0) / first.length
  const eastScale = METERS_PER_DEGREE * Math.cos(lat0 * Math.PI / 180)

  const recent: TrackPoint[] = []
  return flight.map(r => {
    if (r.gps_lat == null || r.gps_lon == null) return null
    recent.push({
      east: (r.gps_lon - lon0) * eastScale,
      north: (r.gps_lat - lat0) * METERS_PER_DEGREE,
    })
    if (recent.length > GPS_SMOOTHING) recent.shift()
    return {
      east: recent.reduce((sum, p) => sum + p.east, 0) / recent.length,
      north: recent.reduce((sum, p) => sum + p.north, 0) / recent.length,
    }
  })
}

/** A round step size that splits `range` into roughly `target` intervals. */
export function niceStep(range: number, target: number): number {
  const raw = range / target
  const magnitude = Math.pow(10, Math.floor(Math.log10(raw)))
  const n = raw / magnitude
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * magnitude
}

/** Index of the entry in an ascending array closest to `value`. */
export function nearestIndex(sorted: number[], value: number): number {
  let lo = 0, hi = sorted.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (sorted[mid] < value) lo = mid
    else hi = mid
  }
  return value - sorted[lo] <= sorted[hi] - value ? lo : hi
}
