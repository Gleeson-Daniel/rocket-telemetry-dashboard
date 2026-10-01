#include "packet.hpp"

#include <cmath>
#include <cstring>
#include <limits>

namespace telemetry {
namespace {

static_assert(std::numeric_limits<float>::is_iec559 && sizeof(float) == 4,
              "packet format assumes IEEE 754 single-precision floats");

class Writer {
public:
    explicit Writer(Packet& out) : out_(out) {}

    void u8(std::uint8_t v) { out_[pos_++] = v; }

    void u16(std::uint16_t v) {
        u8(static_cast<std::uint8_t>(v & 0xFF));
        u8(static_cast<std::uint8_t>(v >> 8));
    }

    void u32(std::uint32_t v) {
        for (int shift = 0; shift < 32; shift += 8)
            u8(static_cast<std::uint8_t>((v >> shift) & 0xFF));
    }

    void u64(std::uint64_t v) {
        for (int shift = 0; shift < 64; shift += 8)
            u8(static_cast<std::uint8_t>((v >> shift) & 0xFF));
    }

    void i32(std::int32_t v) { u32(static_cast<std::uint32_t>(v)); }

    void f32(float v) {
        std::uint32_t bits;
        std::memcpy(&bits, &v, sizeof bits);
        u32(bits);
    }

    std::size_t position() const { return pos_; }

private:
    Packet& out_;
    std::size_t pos_ = 0;
};

std::int32_t scaled_degrees(double degrees) {
    return static_cast<std::int32_t>(std::lround(degrees * 1e7));
}

}  // namespace

std::uint16_t crc16_ccitt(const std::uint8_t* data, std::size_t len) {
    std::uint16_t crc = 0xFFFF;
    for (std::size_t i = 0; i < len; ++i) {
        crc ^= static_cast<std::uint16_t>(data[i] << 8);
        for (int bit = 0; bit < 8; ++bit) {
            const bool top_bit_set = (crc & 0x8000) != 0;
            crc = static_cast<std::uint16_t>(crc << 1);
            if (top_bit_set) crc ^= 0x1021;
        }
    }
    return crc;
}

Packet encode_packet(const Reading& r) {
    Packet packet{};
    Writer w(packet);

    w.u16(SYNC_WORD);
    w.u8(PROTOCOL_VERSION);
    w.u8(r.flight_id);
    w.u32(r.sequence);
    w.u64(r.timestamp_ms);
    w.f32(r.accel_x);
    w.f32(r.accel_y);
    w.f32(r.accel_z);
    w.f32(r.gyro_x);
    w.f32(r.gyro_y);
    w.f32(r.gyro_z);
    w.f32(r.pressure_hpa);
    w.f32(r.altitude_m);
    w.i32(scaled_degrees(r.gps_lat));
    w.i32(scaled_degrees(r.gps_lon));
    w.f32(r.temperature_c);
    w.f32(r.battery_v);
    w.u16(crc16_ccitt(packet.data(), w.position()));

    return packet;
}

}  // namespace telemetry
