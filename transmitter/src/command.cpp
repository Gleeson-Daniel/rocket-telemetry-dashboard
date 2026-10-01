#include "command.hpp"

#include <cstring>

namespace telemetry {
namespace {

class Reader {
public:
    explicit Reader(const std::uint8_t* data) : data_(data) {}

    std::uint8_t u8() { return data_[pos_++]; }

    std::uint16_t u16() {
        const std::uint16_t low = u8();
        const std::uint16_t high = u8();
        return static_cast<std::uint16_t>(low | (high << 8));
    }

    std::uint32_t u32() {
        std::uint32_t v = 0;
        for (int shift = 0; shift < 32; shift += 8)
            v |= static_cast<std::uint32_t>(u8()) << shift;
        return v;
    }

    float f32() {
        const std::uint32_t bits = u32();
        float v;
        std::memcpy(&v, &bits, sizeof v);
        return v;
    }

private:
    const std::uint8_t* data_;
    std::size_t pos_ = 0;
};

}  // namespace

std::optional<Command> decode_command(const std::uint8_t* data, std::size_t len) {
    if (len != COMMAND_SIZE) return std::nullopt;

    Reader r(data);
    if (r.u16() != COMMAND_SYNC_WORD) return std::nullopt;
    const std::uint8_t version = r.u8();
    const std::uint8_t type = r.u8();

    Command command;
    command.config.dry_mass_kg = r.f32();
    command.config.propellant_mass_kg = r.f32();
    command.config.thrust_n = r.f32();
    command.config.burn_time_s = r.f32();
    command.config.diameter_m = r.f32();
    command.config.drag_coefficient = r.f32();
    command.config.chute_diameter_m = r.f32();
    command.config.chute_drag_coefficient = r.f32();

    if (r.u16() != crc16_ccitt(data, COMMAND_SIZE - 2)) return std::nullopt;
    if (version != PROTOCOL_VERSION) return std::nullopt;

    if (type < static_cast<std::uint8_t>(CommandType::Launch) ||
        type > static_cast<std::uint8_t>(CommandType::Resume)) {
        return std::nullopt;
    }
    command.type = static_cast<CommandType>(type);
    return command;
}

}  // namespace telemetry
