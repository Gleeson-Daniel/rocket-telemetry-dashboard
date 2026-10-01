import type { PhaseTransition } from '../hooks/useTelemetry'
import { flightName } from '../flight'

// What a change of phase means in words
function eventName(t: PhaseTransition) {
  switch (t.to_phase) {
    case 'POWERED_ASCENT': return 'Liftoff'
    case 'COAST': return t.from_phase === 'PAD' ? 'Picked up mid-flight' : 'Motor burnout'
    case 'APOGEE': return 'Apogee'
    case 'DESCENT': return 'Descending'
    case 'LANDED': return 'Landed'
    case 'PAD': return 'Back on the pad'
  }
}

/** Every phase change the ground station has detected, newest first. */
export default function EventLog({ transitions }: { transitions: PhaseTransition[] }) {
  return (
    <section>
      <h2>Events <span>detected by the ground station</span></h2>
      {transitions.length === 0
        ? <p className="empty">Nothing yet. Events appear here once a flight starts.</p>
        : (
          <table className="log">
            <thead>
              <tr><th>Time</th><th>Flight</th><th>Event</th><th className="num">Altitude</th></tr>
            </thead>
            <tbody>
              {[...transitions].reverse().map(t => (
                <tr key={`${t.timestamp}-${t.to_phase}`}>
                  <td className="dim">{new Date(t.timestamp).toLocaleTimeString()}</td>
                  <td className="dim">{flightName(t.flight_id)}</td>
                  <td>{eventName(t)}</td>
                  <td className="num">{t.altitude_m.toFixed(1)} m</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </section>
  )
}
