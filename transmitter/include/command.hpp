#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>

#include "flight_sim.hpp"

namespace telemetry {

// Uplink format: commands from the ground station to the rocket.
// Little-endian, 38 bytes. The Python encoder in backend/commands.py must
// match this table exactly.
//
//   offset  size  type  field
//   0       2     u16   sync word (0xC33C)
//   2       1     u8    protocol version
//   3       1     u8    command: 1 = launch, 2 = reset to pad,
//                       3 = pause, 4 = resume
//   4       4     f32   dry mass, kg
//   8       4     f32   propellant mass, kg
//   12      4     f32   average thrust, N
//   16      4     f32   burn time, s
//   20      4     f32   body diameter, m
//   24      4     f32   drag coefficient
//   28      4     f32   parachute diameter, m
//   32      4     f32   parachute drag coefficient
//   36      2     u16   CRC-16/CCITT-FALSE over bytes 0..35
//
// Every command carries the rocket fields; only launch uses them.
constexpr std::uint16_t COMMAND_SYNC_WORD = 0xC33C;
constexpr std::size_t COMMAND_SIZE = 38;

enum class CommandType : std::uint8_t { Launch = 1, Reset = 2, Pause = 3, Resume = 4 };

struct Command {
    CommandType type;
    RocketConfig config;
};

// Returns nothing if the bytes are the wrong length, fail the CRC, or carry
// an unknown version or command.
std::optional<Command> decode_command(const std::uint8_t* data, std::size_t len);

}  // namespace telemetry
