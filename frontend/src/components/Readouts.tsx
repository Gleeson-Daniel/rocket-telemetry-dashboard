import type { LinkStats, TelemetryReading } from '../hooks/useTelemetry'
import { fmt } from '../flight'

const LOW_BATTERY_V = 3.7

function Row({ label, value, unit, flag, gap = false }: {
  label: string; value: string; unit?: string; flag?: string; gap?: boolean
}) {
  return (
    <tr className={gap ? 'gap' : undefined}>
      <td>{label}</td>
      <td className="num">
        {flag && <span className="flag">▲ {flag}</span>}
        {value}<span className="u">{unit}</span>
      </td>
    </tr>
  )
}

/** Every current sensor value, as a column of numbers that line up. */
export function SensorReadouts({ latest, verticalSpeed, distance }: {
  latest: TelemetryReading | null
  verticalSpeed: number | null
  distance: number | null
}) {
  const lowBattery = latest?.battery_v != null && latest.battery_v < LOW_BATTERY_V
  return (
    <section>
      <h2>Sensors</h2>
      <table className="readouts">
        <tbody>
          <Row label="Vertical speed" value={fmt(verticalSpeed, 1)} unit="m/s" />
          <Row label="Acceleration" value={fmt(latest?.imu_accel_z, 2)} unit="m/s²" />
          <Row label="Roll rate" value={fmt(latest?.imu_gyro_z, 2)} unit="rad/s" />
          <Row label="Pressure" value={fmt(latest?.pressure_hpa, 1)} unit="hPa" />
          <Row label="Temperature" value={fmt(latest?.temperature_c, 1)} unit="°C" />
          <Row label="Battery" value={fmt(latest?.battery_v, 2)} unit="V"
            flag={lowBattery ? 'Low' : undefined} />
          <Row gap label="Latitude" value={fmt(latest?.gps_lat, 6)} unit="°" />
          <Row label="Longitude" value={fmt(latest?.gps_lon, 6)} unit="°" />
          <Row label="Distance from pad" value={fmt(distance, 0)} unit="m" />
        </tbody>
      </table>
    </section>
  )
}

/** How well the packets are getting through. */
export function LinkReadouts({ link }: { link: LinkStats | null }) {
  const sent = link ? link.accepted + link.lost : 0
  const delivered = link && sent > 0 ? (100 * link.accepted / sent).toFixed(1) : '–'
  const count = (n: number | undefined) => n == null ? '–' : n.toLocaleString('en-US')
  return (
    <section>
      <h2>Radio link <span>66-byte packets, CRC-16</span></h2>
      <table className="readouts">
        <tbody>
          <Row label="Received" value={count(link?.received)} />
          <Row label="Accepted" value={count(link?.accepted)} />
          <Row label="Failed checksum" value={count(link?.corrupted)} />
          <Row label="Lost" value={count(link?.lost)} />
          <Row label="Out of order" value={count(link?.out_of_order)} />
          <Row gap label="Delivered" value={delivered} unit="%" />
        </tbody>
      </table>
    </section>
  )
}
