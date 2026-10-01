#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace telemetry {

// Wire format, little-endian, 66 bytes. The Python decoder in
// backend/protocol.py must match this table exactly.
//
//   offset  size  type    field
//   0       2     u16     sync word (0xA55A)
//   2       1     u8      protocol version
//   3       1     u8      flight id
//   4       4     u32     sequence number
//   8       8     u64     timestamp, ms since Unix epoch
//   16      12    f32[3]  accelerometer x/y/z, m/s^2 (specific force)
//   28      12    f32[3]  gyroscope x/y/z, rad/s
//   40      4     f32     pressure, hPa
//   44      4     f32     altitude above the pad, m
//   48      4     i32     latitude, degrees * 1e7
//   52      4     i32     longitude, degrees * 1e7
//   56      4     f32     temperature, C
//   60      4     f32     battery, V
//   64      2     u16     CRC-16/CCITT-FALSE over bytes 0..63
constexpr std::uint16_t SYNC_WORD = 0xA55A;
constexpr std::uint8_t PROTOCOL_VERSION = 1;
constexpr std::size_t PACKET_SIZE = 66;

using Packet = std::array<std::uint8_t, PACKET_SIZE>;

struct Reading {
    std::uint8_t flight_id = 0;
    std::uint32_t sequence = 0;
    std::uint64_t timestamp_ms = 0;
    float accel_x = 0, accel_y = 0, accel_z = 0;
    float gyro_x = 0, gyro_y = 0, gyro_z = 0;
    float pressure_hpa = 0;
    float altitude_m = 0;
    // A float32 only resolves 2e-6 to 8e-6 degrees here (20 to 70 cm), so
    // position is kept as a double and sent as a scaled int32 (about 1 cm).
    double gps_lat = 0, gps_lon = 0;
    float temperature_c = 0;
    float battery_v = 0;
};

// CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no final XOR.
std::uint16_t crc16_ccitt(const std::uint8_t* data, std::size_t len);

// Serializes field by field rather than copying the struct, so the bytes on
// the wire don't depend on compiler padding or the host's endianness.
Packet encode_packet(const Reading& reading);

}  // namespace telemetry
