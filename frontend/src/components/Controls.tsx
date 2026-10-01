import { useState } from 'react'
import { post } from '../api'
import type { StationStatus } from '../hooks/useTelemetry'

const ROCKET_FIELDS = [
  { key: 'dry_mass_kg', label: 'Dry mass', unit: 'kg', value: '2.0' },
  { key: 'propellant_mass_kg', label: 'Propellant mass', unit: 'kg', value: '0.3' },
  { key: 'thrust_n', label: 'Average thrust', unit: 'N', value: '120' },
  { key: 'burn_time_s', label: 'Burn time', unit: 's', value: '2.5' },
  { key: 'diameter_m', label: 'Body diameter', unit: 'm', value: '0.066' },
  { key: 'drag_coefficient', label: 'Drag coefficient', unit: '', value: '0.5' },
  { key: 'chute_diameter_m', label: 'Parachute diameter', unit: 'm', value: '0.6' },
  { key: 'chute_drag_coefficient', label: 'Parachute drag coefficient', unit: '', value: '0.8' },
]

const REPLAY_SPEEDS = [1, 2, 5, 10]

interface Estimate {
  thrust_to_weight: number
  descent_rate_ms: number
  total_impulse_ns: number
  motor_class: string
}

interface LogInfo {
  samples: number
  duration_s: number
  peak_altitude_m: number
  accel_source: string
  missing: string[]
}

type Mode = 'rocket' | 'log'
type Notice = { ok: boolean; text: string } | null

/** Choose what to run (a rocket to simulate or a log to replay) and run it. */
export default function Controls({ status, onChange }: {
  status: StationStatus | null
  onChange: () => void  // called after any action so the status refreshes at once
}) {
  const [mode, setMode] = useState<Mode>('rocket')
  const [spec, setSpec] = useState<Record<string, string>>(
    Object.fromEntries(ROCKET_FIELDS.map(f => [f.key, f.value])))
  const [file, setFile] = useState<File | null>(null)
  const [speed, setSpeed] = useState(1)
  const [notice, setNotice] = useState<Notice>(null)
  const [busy, setBusy] = useState(false)

  const paused = status?.paused ?? false
  const replay = status?.source.mode === 'replay' ? status.source : null

  const run = async (action: () => Promise<Notice>) => {
    setBusy(true)
    setNotice(await action())
    setBusy(false)
    onChange()
  }

  const start = () => run(async () => {
    if (mode === 'rocket') {
      const numbers = Object.fromEntries(
        Object.entries(spec).map(([key, value]) => [key, Number(value)]))
      const result = await post<Estimate>('launch', numbers)
      if (!result.ok) return { ok: false, text: result.error }
      const e = result.data
      return { ok: true, text:
        `Launched. ${e.motor_class}-class motor (${e.total_impulse_ns} N·s), ` +
        `thrust-to-weight ${e.thrust_to_weight}, ` +
        `descent under parachute about ${e.descent_rate_ms} m/s.` }
    }

    if (!file) return { ok: false, text: 'Choose a CSV file first.' }
    const form = new FormData()
    form.append('file', file)
    form.append('speed', String(speed))
    const result = await post<LogInfo>('replay', form)
    if (!result.ok) return { ok: false, text: result.error }
    const info = result.data
    const missing = info.missing.length ? ` Not in the log: ${info.missing.join(', ')}.` : ''
    return { ok: true, text:
      `Replaying ${info.duration_s} s of flight, peak ${info.peak_altitude_m} m. ` +
      `Acceleration: ${info.accel_source}.${missing}` }
  })

  const pauseOrResume = () => run(async () => {
    const result = await post(paused ? 'resume' : 'pause')
    return result.ok ? null : { ok: false, text: result.error }
  })

  const stop = () => run(async () => {
    const result = await post('stop')
    if (!result.ok) return { ok: false, text: result.error }
    return { ok: true, text: replay ? 'Replay stopped.' : 'Stopped. The rocket is back on the pad.' }
  })

  return (
    <section>
      <h2>Simulation</h2>

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={mode === 'rocket'}
          onClick={() => setMode('rocket')}>Simulate a rocket</button>
        <button role="tab" aria-selected={mode === 'log'}
          onClick={() => setMode('log')}>Replay a flight log</button>
      </div>

      {mode === 'rocket' ? (
        <div className="spec">
          {ROCKET_FIELDS.map(f => [
            <label key={`${f.key}-label`} htmlFor={f.key}>{f.label}</label>,
            <input key={f.key} id={f.key} type="number" step="any" min="0"
              value={spec[f.key]}
              onChange={e => setSpec({ ...spec, [f.key]: e.target.value })} />,
            <span key={`${f.key}-unit`} className="unit">{f.unit}</span>,
          ])}
        </div>
      ) : (
        <div>
          <label className="field">
            <span>CSV file</span>
            <input type="file" accept=".csv,.txt,text/csv"
              onChange={e => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <label className="field">
            <span>Playback speed</span>
            <select value={speed} onChange={e => setSpeed(Number(e.target.value))}>
              {REPLAY_SPEEDS.map(s => <option key={s} value={s}>{s}×</option>)}
            </select>
          </label>
          <p className="hint">
            Needs a time column in seconds and an altitude column. Acceleration
            is used if the file has it and worked out from altitude if not.
          </p>
        </div>
      )}

      <div className="transport">
        <button className="primary" onClick={start} disabled={busy}>Start</button>
        <button onClick={pauseOrResume} disabled={busy}>{paused ? 'Resume' : 'Pause'}</button>
        <button onClick={stop} disabled={busy}>Stop</button>
      </div>

      {replay && (
        <div className="progress">
          {replay.name}, {Math.round(replay.progress * 100)}% played
          <div className="bar"><div style={{ width: `${replay.progress * 100}%` }} /></div>
        </div>
      )}
      {notice && <p className={notice.ok ? 'notice ok' : 'notice bad'}>{notice.text}</p>}
    </section>
  )
}
