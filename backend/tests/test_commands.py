import struct

import pytest
from pydantic import ValidationError

from commands import (
    COMMAND_LAUNCH, COMMAND_RESET, COMMAND_SIZE, RocketSpec, encode_command,
    estimate, motor_class, problems,
)
from protocol import crc16_ccitt

# The same bytes are hard-coded in transmitter/tests/test_packet.cpp, where
# the C++ decoder is checked against them.
GOLDEN_SPEC = RocketSpec(
    dry_mass_kg=1.5, propellant_mass_kg=0.25, thrust_n=100, burn_time_s=2,
    diameter_m=0.05, drag_coefficient=0.75, chute_diameter_m=0.5,
    chute_drag_coefficient=1.25,
)
GOLDEN_LAUNCH = bytes.fromhex(
    "3cc301010000c03f0000803e0000c84200000040cdcc4c3d0000403f0000003f0000a03fa1b5"
)


def test_launch_command_matches_the_bytes_the_cpp_decoder_is_tested_against():
    assert encode_command(COMMAND_LAUNCH, GOLDEN_SPEC) == GOLDEN_LAUNCH


def test_command_layout():
    command = encode_command(COMMAND_RESET)

    assert len(command) == COMMAND_SIZE == 38
    assert command[0:2] == b"\x3c\xc3"
    assert command[2] == 1
    assert command[3] == COMMAND_RESET
    assert struct.unpack("<H", command[-2:])[0] == crc16_ccitt(command[:-2])


def test_default_rocket_has_no_problems():
    assert problems(RocketSpec()) == []


def test_estimates_for_the_default_rocket():
    figures = estimate(RocketSpec())

    assert figures["thrust_to_weight"] == pytest.approx(120 / (2.3 * 9.81), abs=0.01)
    assert figures["total_impulse_ns"] == 300
    assert figures["motor_class"] == "H"
    assert figures["descent_rate_ms"] == pytest.approx(11.9, abs=0.1)


def test_rocket_too_heavy_to_lift_off_is_refused():
    issues = problems(RocketSpec(thrust_n=20))

    assert len(issues) == 1
    assert "never leave the pad" in issues[0]


def test_parachute_too_large_for_the_landing_detector_is_refused():
    issues = problems(RocketSpec(chute_diameter_m=3.0))

    assert len(issues) == 1
    assert "parachute is too large" in issues[0]


@pytest.mark.parametrize("field", RocketSpec.model_fields)
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_nonsense_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        RocketSpec(**{field: value})


@pytest.mark.parametrize("impulse,letter", [
    (2.5, "A"), (5.01, "C"), (40, "E"), (160, "G"), (300, "H"), (320.1, "I"), (1e6, "O+"),
])
def test_motor_class(impulse, letter):
    assert motor_class(impulse) == letter
