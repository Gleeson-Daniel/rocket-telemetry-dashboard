import { useTelemetry } from './hooks/useTelemetry'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend
} from 'recharts'

function StatusCard({ label, value, unit, color }: {
  label: string; value: string | number; unit: string; color: string
}) {
  return (
    <div style={{
      background: '#13161e', border: '1px solid #1e2230',
      borderTop: `3px solid ${color}`, borderRadius: 10,
      padding: '16px 20px', minWidth: 140
    }}>
      <div style={{ fontSize: 11, color: '#6b7391', marginBottom: 6,
        fontFamily: 'monospace', textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 600, color: '#fff' }}>
        {value}<span style={{ fontSize: 13, color: '#6b7391',
          marginLeft: 4 }}>{unit}</span>
      </div>
    </div>
  )
}

export default function App() {
  const { readings, latest, connected } = useTelemetry()

  const chartData = readings.map(r => ({
    time: new Date(r.timestamp).toLocaleTimeString(),
    altitude: r.altitude_m,
    temperature: r.temperature_c,
    pressure: r.pressure_hpa,
  }))

  return (
    <div style={{ background: '#0a0b0f', minHeight: '100vh',
      color: '#d8dce8', padding: 28, fontFamily: 'DM Sans, sans-serif' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: 11, fontFamily: 'monospace',
            color: '#6b7391', marginBottom: 4 }}>ROCKET TELEMETRY SYSTEM</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#fff',
            margin: 0 }}>Live Dashboard</h1>
        </div>
        <div style={{
          padding: '6px 14px', borderRadius: 999,
          background: connected ? 'rgba(52,211,153,0.1)' : 'rgba(251,113,133,0.1)',
          border: `1px solid ${connected ? 'rgba(52,211,153,0.3)' : 'rgba(251,113,133,0.3)'}`,
          color: connected ? '#34d399' : '#fb7185',
          fontSize: 12, fontFamily: 'monospace'
        }}>
          {connected ? '● LIVE' : '○ CONNECTING'}
        </div>
      </div>

      {/* Status Cards */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 28 }}>
        <StatusCard label="Altitude" value={latest?.altitude_m.toFixed(1) ?? '--'} unit="m" color="#38bdf8" />
        <StatusCard label="Temperature" value={latest?.temperature_c.toFixed(1) ?? '--'} unit="°C" color="#f97316" />
        <StatusCard label="Pressure" value={latest?.pressure_hpa.toFixed(1) ?? '--'} unit="hPa" color="#a78bfa" />
        <StatusCard label="Battery" value={latest?.battery_v.toFixed(2) ?? '--'} unit="V" color={
          (latest?.battery_v ?? 4) > 3.7 ? '#34d399' : '#fb7185'
        } />
        <StatusCard label="Accel Z" value={latest?.imu_accel_z.toFixed(3) ?? '--'} unit="m/s²" color="#fbbf24" />
      </div>

      {/* Altitude Chart */}
      <div style={{ background: '#111318', border: '1px solid #1e2230',
        borderRadius: 10, padding: '20px 16px', marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontFamily: 'monospace', color: '#6b7391',
          marginBottom: 16 }}>ALTITUDE · {readings.length} readings</div>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2230" />
            <XAxis dataKey="time" tick={{ fill: '#6b7391', fontSize: 10 }}
              interval="preserveStartEnd" />
            <YAxis tick={{ fill: '#6b7391', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#111318',
              border: '1px solid #1e2230', borderRadius: 6 }} />
            <Line type="monotone" dataKey="altitude" stroke="#38bdf8"
              dot={false} strokeWidth={2} name="Altitude (m)" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Temperature + Pressure Chart */}
      <div style={{ background: '#111318', border: '1px solid #1e2230',
        borderRadius: 10, padding: '20px 16px' }}>
        <div style={{ fontSize: 13, fontFamily: 'monospace', color: '#6b7391',
          marginBottom: 16 }}>TEMPERATURE & PRESSURE</div>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2230" />
            <XAxis dataKey="time" tick={{ fill: '#6b7391', fontSize: 10 }}
              interval="preserveStartEnd" />
            <YAxis yAxisId="temp" tick={{ fill: '#f97316', fontSize: 10 }} />
            <YAxis yAxisId="pres" orientation="right"
              tick={{ fill: '#a78bfa', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#111318',
              border: '1px solid #1e2230', borderRadius: 6 }} />
            <Legend />
            <Line yAxisId="temp" type="monotone" dataKey="temperature"
              stroke="#f97316" dot={false} strokeWidth={2} name="Temp (°C)" />
            <Line yAxisId="pres" type="monotone" dataKey="pressure"
              stroke="#a78bfa" dot={false} strokeWidth={2} name="Pressure (hPa)" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}