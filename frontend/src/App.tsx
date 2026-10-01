import { useMemo, useState } from 'react'
import { useTelemetry } from './hooks/useTelemetry'
import type { StationStatus } from './hooks/useTelemetry'
import {
  currentFlight, flightName, groundTrack, launchTimestamp, nearestIndex, verticalSpeed,
} from './flight'
import Controls from './components/Controls'
import Headline from './components/Headline'
import FlightCharts from './components/FlightCharts'
import GroundTrack from './components/GroundTrack'
import EventLog from './components/EventLog'
import { LinkReadouts, SensorReadouts } from './components/Readouts'

// What the page is showing right now. Each state has its own icon as well as
// its own colour, so it can be read without relying on colour.
function describe(connected: boolean, status: StationStatus | null) {
  if (!connected || !status) return { kind: 'critical', icon: '✕', text: 'Backend offline' }
  if (status.paused) return { kind: 'warning', icon: 'Ⅱ', text: 'Paused' }
  if (status.source.mode === 'replay') {
    return { kind: 'info', icon: '▶', text: `Replaying ${status.source.name}` }
  }
  if (status.transmitter_connected) return { kind: 'good', icon: '✓', text: 'Receiving telemetry' }
  return { kind: 'critical', icon: '!', text: 'No signal from the transmitter' }
}

export default function App() {
  const {
    readings, latest, transitions, link, summary, status, connected, refreshStatus,
  } = useTelemetry()
  const [hoverTime, setHoverTime] = useState<number | null>(null)

  const flight = useMemo(() => currentFlight(readings), [readings])
  const launchedAt = useMemo(() => launchTimestamp(flight), [flight])
  const track = useMemo(() => groundTrack(flight), [flight])

  // Seconds from launch once there has been one; before that, seconds
  // before now, so the pad wait reads as a scrolling window.
  const times = useMemo(() => {
    const zero = launchedAt ?? flight[flight.length - 1]?.timestamp ?? 0
    return flight.map(r => (r.timestamp - zero) / 1000)
  }, [flight, launchedAt])
  const hoverIndex = hoverTime != null && times.length ? nearestIndex(times, hoverTime) : null

  const launchIndex = launchedAt != null
    ? flight.findIndex(r => r.timestamp >= launchedAt) : null
  const position = track?.[track.length - 1]
  const distance = position ? Math.hypot(position.east, position.north) : null
  const state = describe(connected, status)

  return (
    <div className="app">
      <header className="topbar">
        <h1>Rocket ground station</h1>
        <span className="source">{flightName(latest?.flight_id)}</span>
        <div className={`status status-${state.kind}`} role="status">
          <span className="status-icon" aria-hidden="true">{state.icon}</span>
          {state.text}
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <Controls status={status} onChange={refreshStatus} />
          <SensorReadouts latest={latest} verticalSpeed={verticalSpeed(flight)}
            distance={distance} />
          <LinkReadouts link={link} />
        </aside>

        <main className="main">
          <Headline flight={flight} launchedAt={launchedAt} summary={summary} />
          <FlightCharts flight={flight} times={times} launched={launchedAt != null}
            hoverIndex={hoverIndex} onHover={setHoverTime} />
          <div className="lower">
            <GroundTrack track={track} launchIndex={launchIndex} hoverIndex={hoverIndex} />
            <EventLog transitions={transitions} />
          </div>
        </main>
      </div>
    </div>
  )
}
