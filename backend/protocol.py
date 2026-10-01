import struct

SYNC_WORD = 0xA55A
PROTOCOL_VERSION = 1

# Little-endian with no padding. Must match the table in
# transmitter/include/packet.hpp:
#   sync u16, version u8, flight id u8, sequence u32, timestamp u64,
#   8 x f32 (accel xyz, gyro xyz, pressure, altitude),
#   2 x i32 (lat, lon in degrees * 1e7), 2 x f32 (temperature, battery)
_BODY = struct.Struct("<HBBIQ8f2i2f")
_CRC = struct.Struct("<H")
PACKET_SIZE = _BODY.size + _CRC.size  # 66 bytes

GPS_SCALE = 1e7


class PacketError(Exception):
    """A datagram that could not be decoded into a reading."""


class BadLength(PacketError):
    pass


class BadSync(PacketError):
    pass


class BadChecksum(PacketError):
    pass


class BadVersion(PacketError):
    pass


def crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc


def decode_packet(data: bytes) -> dict:
    if len(data) != PACKET_SIZE:
        raise BadLength(f"expected {PACKET_SIZE} bytes, got {len(data)}")

    body = data[:_BODY.size]
    (sync, version, flight_id, seq, timestamp,
     accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z,
     pressure, altitude, lat, lon, temperature, battery) = _BODY.unpack(body)

    if sync != SYNC_WORD:
        raise BadSync(f"sync word 0x{sync:04X}")
    (expected_crc,) = _CRC.unpack(data[_BODY.size:])
    if crc16_ccitt(body) != expected_crc:
        raise BadChecksum(f"packet {seq} failed its CRC")
    if version != PROTOCOL_VERSION:
        raise BadVersion(f"protocol version {version}")

    # float32 values come back with noise in the low digits (9.81 becomes
    # 9.8100004196...), so round to what each sensor can actually resolve.
    return {
        "flight_id": flight_id,
        "seq": seq,
        "timestamp": timestamp,
        "imu_accel_x": round(accel_x, 4),
        "imu_accel_y": round(accel_y, 4),
        "imu_accel_z": round(accel_z, 4),
        "imu_gyro_x": round(gyro_x, 4),
        "imu_gyro_y": round(gyro_y, 4),
        "imu_gyro_z": round(gyro_z, 4),
        "pressure_hpa": round(pressure, 2),
        "altitude_m": round(altitude, 2),
        "gps_lat": round(lat / GPS_SCALE, 7),
        "gps_lon": round(lon / GPS_SCALE, 7),
        "temperature_c": round(temperature, 2),
        "battery_v": round(battery, 3),
    }


def encode_packet(reading: dict) -> bytes:
    """Python twin of the C++ encoder, used to build packets in tests."""
    body = _BODY.pack(
        SYNC_WORD, PROTOCOL_VERSION, reading["flight_id"], reading["seq"],
        reading["timestamp"],
        reading["imu_accel_x"], reading["imu_accel_y"], reading["imu_accel_z"],
        reading["imu_gyro_x"], reading["imu_gyro_y"], reading["imu_gyro_z"],
        reading["pressure_hpa"], reading["altitude_m"],
        round(reading["gps_lat"] * GPS_SCALE), round(reading["gps_lon"] * GPS_SCALE),
        reading["temperature_c"], reading["battery_v"],
    )
    return body + _CRC.pack(crc16_ccitt(body))


class SequenceTracker:
    """Rejects packets that arrive late or twice, and counts the gaps.

    A late packet is counted twice: once in `lost` when its number was
    skipped, and again in `out_of_order` when it finally shows up and is
    thrown away.
    """

    # A sequence number this far behind the newest one means the transmitter
    # restarted and began counting from zero again, not that a packet is late.
    RESTART_GAP = 50

    def __init__(self):
        self.last = None
        self.lost = 0
        self.out_of_order = 0

    def accept(self, seq: int) -> bool:
        if self.last is None or seq > self.last:
            if self.last is not None:
                self.lost += seq - self.last - 1
            self.last = seq
            return True
        if self.last - seq > self.RESTART_GAP:
            self.last = seq
            return True
        self.out_of_order += 1
        return False
