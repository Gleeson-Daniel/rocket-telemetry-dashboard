import math
import struct

from pydantic import BaseModel, Field

from protocol import PROTOCOL_VERSION, crc16_ccitt

COMMAND_SYNC_WORD = 0xC33C
COMMAND_LAUNCH = 1
COMMAND_RESET = 2
COMMAND_PAUSE = 3
COMMAND_RESUME = 4

# Little-endian with no padding. Must match the table in
# transmitter/include/command.hpp:
#   sync u16, version u8, command u8, 8 x f32 rocket parameters
_BODY = struct.Struct("<HBB8f")
_CRC = struct.Struct("<H")
COMMAND_SIZE = _BODY.size + _CRC.size  # 38 bytes

G = 9.81
AIR_DENSITY = 1.225  # kg/m^3 at sea level

# The landing detector calls the rocket landed once altitude changes by less
# than 3 m in a second, so anything descending slower than this would be
# declared landed while still in the air.
MIN_DESCENT_RATE = 4.0  # m/s

# Total impulse at the top of each hobby motor class, in newton-seconds.
# Each class is twice the one before it.
_MOTOR_CLASSES = [(2.5 * 2 ** i, letter) for i, letter in enumerate("ABCDEFGHIJKLMNO")]


class RocketSpec(BaseModel):
    dry_mass_kg: float = Field(2.0, gt=0, le=50)
    propellant_mass_kg: float = Field(0.3, gt=0, le=20)
    thrust_n: float = Field(120.0, gt=0, le=10000)
    burn_time_s: float = Field(2.5, gt=0, le=20)
    diameter_m: float = Field(0.066, gt=0, le=0.5)
    drag_coefficient: float = Field(0.5, gt=0, le=2)
    chute_diameter_m: float = Field(0.6, gt=0, le=5)
    chute_drag_coefficient: float = Field(0.8, gt=0, le=2.5)


def encode_command(command: int, spec: RocketSpec = None) -> bytes:
    spec = spec or RocketSpec()
    body = _BODY.pack(
        COMMAND_SYNC_WORD, PROTOCOL_VERSION, command,
        spec.dry_mass_kg, spec.propellant_mass_kg, spec.thrust_n, spec.burn_time_s,
        spec.diameter_m, spec.drag_coefficient,
        spec.chute_diameter_m, spec.chute_drag_coefficient,
    )
    return body + _CRC.pack(crc16_ccitt(body))


def motor_class(total_impulse_ns: float) -> str:
    for upper_limit, letter in _MOTOR_CLASSES:
        if total_impulse_ns <= upper_limit:
            return letter
    return "O+"


def estimate(spec: RocketSpec) -> dict:
    """Quick hand calculations shown to the user before the flight plays out."""
    liftoff_weight = (spec.dry_mass_kg + spec.propellant_mass_kg) * G
    chute_area = math.pi * spec.chute_diameter_m ** 2 / 4
    descent_rate = math.sqrt(
        2 * spec.dry_mass_kg * G / (AIR_DENSITY * spec.chute_drag_coefficient * chute_area)
    )
    total_impulse = spec.thrust_n * spec.burn_time_s
    return {
        "thrust_to_weight": round(spec.thrust_n / liftoff_weight, 2),
        "descent_rate_ms": round(descent_rate, 1),
        "total_impulse_ns": round(total_impulse, 1),
        "motor_class": motor_class(total_impulse),
    }


def problems(spec: RocketSpec) -> list:
    """Reasons this rocket can't be flown, as sentences for the user."""
    figures = estimate(spec)
    found = []
    if figures["thrust_to_weight"] <= 1.0:
        weight = (spec.dry_mass_kg + spec.propellant_mass_kg) * G
        found.append(
            f"Thrust of {spec.thrust_n:g} N is not more than the rocket's weight of "
            f"{weight:.1f} N, so it would never leave the pad."
        )
    if figures["descent_rate_ms"] < MIN_DESCENT_RATE:
        found.append(
            f"The parachute is too large: descent would be {figures['descent_rate_ms']} m/s, "
            f"and the landing detector needs at least {MIN_DESCENT_RATE:g} m/s."
        )
    return found
