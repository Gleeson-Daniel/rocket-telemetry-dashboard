#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>

#include "check.hpp"
#include "command.hpp"
#include "packet.hpp"

namespace {

telemetry::Reading sample_reading() {
    telemetry::Reading r;
    r.flight_id = 7;
    r.sequence = 0x01020304;
    r.timestamp_ms = 0x0102030405060708ULL;
    r.accel_x = 1.0f;
    r.accel_z = -2.0f;
    r.gps_lat = 29.6516;
    r.gps_lon = -82.3248;
    r.battery_v = 4.2f;
    return r;
}

// A launch command produced by the Python encoder in backend/commands.py, for
// a rocket with dry mass 1.5, propellant 0.25, thrust 100, burn time 2,
// diameter 0.05, drag coefficient 0.75, chute diameter 0.5, chute Cd 1.25.
// backend/tests/test_commands.py checks Python still produces these bytes.
using CommandBytes = std::array<std::uint8_t, telemetry::COMMAND_SIZE>;
const CommandBytes LAUNCH_COMMAND = {
    0x3C, 0xC3, 0x01, 0x01, 0x00, 0x00, 0xC0, 0x3F, 0x00, 0x00, 0x80, 0x3E, 0x00,
    0x00, 0xC8, 0x42, 0x00, 0x00, 0x00, 0x40, 0xCD, 0xCC, 0x4C, 0x3D, 0x00, 0x00,
    0x40, 0x3F, 0x00, 0x00, 0x00, 0x3F, 0x00, 0x00, 0xA0, 0x3F, 0xA1, 0xB5};

void test_crc_matches_published_check_value() {
    const char* text = "123456789";
    const auto* bytes = reinterpret_cast<const std::uint8_t*>(text);
    CHECK(telemetry::crc16_ccitt(bytes, std::strlen(text)) == 0x29B1);
}

void test_header_is_little_endian() {
    const telemetry::Packet p = telemetry::encode_packet(sample_reading());
    CHECK(p.size() == 66);
    CHECK(p[0] == 0x5A && p[1] == 0xA5);
    CHECK(p[2] == telemetry::PROTOCOL_VERSION);
    CHECK(p[3] == 7);
    CHECK(p[4] == 0x04 && p[5] == 0x03 && p[6] == 0x02 && p[7] == 0x01);
    CHECK(p[8] == 0x08 && p[15] == 0x01);
}

void test_payload_fields_land_at_documented_offsets() {
    const telemetry::Packet p = telemetry::encode_packet(sample_reading());
    // 1.0f is 0x3F800000 and -2.0f is 0xC0000000 in IEEE 754.
    CHECK(p[16] == 0x00 && p[17] == 0x00 && p[18] == 0x80 && p[19] == 0x3F);
    CHECK(p[24] == 0x00 && p[25] == 0x00 && p[26] == 0x00 && p[27] == 0xC0);
    // 29.6516 degrees * 1e7 = 296516000 = 0x11AC79A0.
    CHECK(p[48] == 0xA0 && p[49] == 0x79 && p[50] == 0xAC && p[51] == 0x11);
    // -82.3248 degrees * 1e7 = -823248000 = 0xCEEE3B80 as two's complement.
    CHECK(p[52] == 0x80 && p[53] == 0x3B && p[54] == 0xEE && p[55] == 0xCE);
}

void test_crc_covers_everything_before_it() {
    telemetry::Packet p = telemetry::encode_packet(sample_reading());
    const std::uint16_t stored = static_cast<std::uint16_t>(p[64] | (p[65] << 8));
    CHECK(stored == telemetry::crc16_ccitt(p.data(), 64));

    p[30] ^= 0x01;
    CHECK(stored != telemetry::crc16_ccitt(p.data(), 64));
}

void test_command_from_python_decodes() {
    const auto command = telemetry::decode_command(LAUNCH_COMMAND.data(), LAUNCH_COMMAND.size());
    CHECK(command.has_value());
    if (!command) return;

    CHECK(command->type == telemetry::CommandType::Launch);
    CHECK(command->config.dry_mass_kg == 1.5);
    CHECK(command->config.propellant_mass_kg == 0.25);
    CHECK(command->config.thrust_n == 100.0);
    CHECK(command->config.burn_time_s == 2.0);
    CHECK(std::fabs(command->config.diameter_m - 0.05) < 1e-6);
    CHECK(command->config.drag_coefficient == 0.75);
    CHECK(command->config.chute_diameter_m == 0.5);
    CHECK(command->config.chute_drag_coefficient == 1.25);
}

void test_corrupted_command_is_rejected() {
    for (std::size_t bit = 0; bit < LAUNCH_COMMAND.size() * 8; ++bit) {
        CommandBytes corrupted = LAUNCH_COMMAND;
        corrupted[bit / 8] ^= static_cast<std::uint8_t>(1u << (bit % 8));
        CHECK(!telemetry::decode_command(corrupted.data(), corrupted.size()));
    }
}

// Returns the launch command with its type byte changed and the CRC redone.
CommandBytes command_of_type(std::uint8_t type) {
    CommandBytes bytes = LAUNCH_COMMAND;
    bytes[3] = type;
    const std::uint16_t crc = telemetry::crc16_ccitt(bytes.data(), bytes.size() - 2);
    bytes[36] = static_cast<std::uint8_t>(crc & 0xFF);
    bytes[37] = static_cast<std::uint8_t>(crc >> 8);
    return bytes;
}

void test_every_command_type_decodes() {
    const telemetry::CommandType types[] = {
        telemetry::CommandType::Launch, telemetry::CommandType::Reset,
        telemetry::CommandType::Pause, telemetry::CommandType::Resume};
    for (const telemetry::CommandType type : types) {
        const CommandBytes bytes = command_of_type(static_cast<std::uint8_t>(type));
        const auto command = telemetry::decode_command(bytes.data(), bytes.size());
        CHECK(command.has_value() && command->type == type);
    }
}

void test_unknown_command_type_is_rejected() {
    for (const std::uint8_t type : {0, 5, 255}) {
        const CommandBytes bytes = command_of_type(type);
        CHECK(!telemetry::decode_command(bytes.data(), bytes.size()));
    }
}

void test_command_of_the_wrong_length_is_rejected() {
    CHECK(!telemetry::decode_command(LAUNCH_COMMAND.data(), LAUNCH_COMMAND.size() - 1));
    CHECK(!telemetry::decode_command(LAUNCH_COMMAND.data(), 0));
}

}  // namespace

int main() {
    test_crc_matches_published_check_value();
    test_header_is_little_endian();
    test_payload_fields_land_at_documented_offsets();
    test_crc_covers_everything_before_it();
    test_command_from_python_decodes();
    test_corrupted_command_is_rejected();
    test_every_command_type_decodes();
    test_unknown_command_type_is_rejected();
    test_command_of_the_wrong_length_is_rejected();
    return report("packet");
}
