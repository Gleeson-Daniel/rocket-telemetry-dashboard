import { useState, useEffect, useRef, useCallback } from 'react'
import { API_URL, WS_URL } from '../api'

export type FlightPhase =
  'PAD' | 'POWERED_ASCENT' | 'COAST' | 'APOGEE' | 'DESCENT' | 'LANDED'

// A channel is null when a replayed flight log didn't record it
export interface TelemetryReading {
  timestamp: number
  imu_accel_x: number | null; imu_accel_y: number | null; imu_accel_z: number
  imu_gyro_x: number | null;  imu_gyro_y: number | null;  imu_gyro_z: number | null
  pressure_hpa: number | null
  altitude_m: number
  gps_lat: number | null; gps_lon: number | null
  temperature_c: number | null
  battery_v: number | null
  // Missing on rows saved before the binary protocol was added
  seq?: number
  flight_id?: number
  phase?: FlightPhase
}

export interface LinkStats {
  received: number
  accepted: number
  corrupted: number
  lost: number
  out_of_order: number
}

export interface PhaseTransition {
  timestamp: number
  flight_id: number
  from_phase: FlightPhase
  to_phase: FlightPhase
  altitude_m: number
}

export interface FlightSummary {
  peak_altitude_m: number
  max_accel_ms2: number
  flight_time_s: number
}

export type TelemetrySource =
  { mode: 'live' } | { mode: 'replay'; name: string; progress: number }

export interface StationStatus {
  source: TelemetrySource
  transmitter_connected: boolean
  paused: boolean
}

interface TelemetryMessage {
  reading: TelemetryReading
  link: LinkStats
  transition: PhaseTransition | null
  summary: FlightSummary
  source: TelemetrySource
}

const MAX_POINTS = 3000  // Five minutes of readings, enough for a long descent
const MAX_TRANSITIONS = 12
const STATUS_POLL_MS = 1000

export function useTelemetry() {
  const [readings, setReadings] = useState<TelemetryReading[]>([])
  const [transitions, setTransitions] = useState<PhaseTransition[]>([])
  const [link, setLink] = useState<LinkStats | null>(null)
  const [summary, setSummary] = useState<FlightSummary | null>(null)
  const [status, setStatus] = useState<StationStatus | null>(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  // Load history on mount
  useEffect(() => {
    fetch(`${API_URL}/history?limit=${MAX_POINTS}`)
      .then(r => r.json())
      .then((data: TelemetryReading[]) => {
        setReadings(data.slice(-MAX_POINTS))
      })
      .catch(console.error)
    fetch(`${API_URL}/transitions?limit=${MAX_TRANSITIONS}`)
      .then(r => r.json())
      .then((data: PhaseTransition[]) => setTransitions(data))
      .catch(console.error)
  }, [])

  // The stream goes quiet when the simulation is paused or the transmitter
  // stops, so those states have to be asked for rather than waited for.
  const refreshStatus = useCallback(() => {
    fetch(`${API_URL}/status`)
      .then(r => r.json())
      .then((data: StationStatus) => setStatus(data))
      .catch(() => setStatus(null))
  }, [])

  useEffect(() => {
    refreshStatus()
    const timer = setInterval(refreshStatus, STATUS_POLL_MS)
    return () => clearInterval(timer)
  }, [refreshStatus])

  // WebSocket connection
  useEffect(() => {
    let closed = false
    const connect = () => {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) setTimeout(connect, 2000)  // Auto-reconnect
      }
      ws.onmessage = (event) => {
        const message: TelemetryMessage = JSON.parse(event.data)
        setReadings(prev => {
          const next = [...prev, message.reading]
          return next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next
        })
        setLink(message.link)
        setSummary(message.summary ?? null)
        const transition = message.transition
        if (transition) {
          setTransitions(prev => [...prev, transition].slice(-MAX_TRANSITIONS))
        }
      }
    }
    connect()
    return () => {
      closed = true
      wsRef.current?.close()
    }
  }, [])

  const latest = readings[readings.length - 1] ?? null

  return { readings, latest, transitions, link, summary, status, connected, refreshStatus }
}
