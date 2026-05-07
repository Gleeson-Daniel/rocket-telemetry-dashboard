import { useState, useEffect, useRef } from 'react'

export interface TelemetryReading {
  timestamp: number
  imu_accel_x: number; imu_accel_y: number; imu_accel_z: number
  imu_gyro_x: number;  imu_gyro_y: number;  imu_gyro_z: number
  pressure_hpa: number
  altitude_m: number
  gps_lat: number; gps_lon: number
  temperature_c: number
  battery_v: number
}

const MAX_POINTS = 100  // Keep last 100 readings on chart
const WS_URL = 'ws://localhost:8000/ws/telemetry'
const API_URL = 'http://localhost:8000/api/history'

export function useTelemetry() {
  const [readings, setReadings] = useState<TelemetryReading[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  // Load history on mount
  useEffect(() => {
    fetch(API_URL)
      .then(r => r.json())
      .then((data: TelemetryReading[]) => {
        setReadings(data.slice(-MAX_POINTS))
      })
      .catch(console.error)
  }, [])

  // WebSocket connection
  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        setTimeout(connect, 2000)  // Auto-reconnect
      }
      ws.onmessage = (event) => {
        const reading: TelemetryReading = JSON.parse(event.data)
        setReadings(prev => {
          const next = [...prev, reading]
          return next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next
        })
      }
    }
    connect()
    return () => wsRef.current?.close()
  }, [])

  const latest = readings[readings.length - 1] ?? null

  return { readings, latest, connected }
}