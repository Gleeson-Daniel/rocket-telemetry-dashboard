"""End-to-end checks against the real C++ transmitter.

Skipped unless the transmitter has been built, either at the default CMake
location or wherever the TRANSMITTER_BIN environment variable points.
"""
import os
import socket
import subprocess
from pathlib import Path

import pytest

from commands import (COMMAND_LAUNCH, COMMAND_PAUSE, COMMAND_RESET, COMMAND_RESUME,
                      RocketSpec, encode_command)
from pipeline import TelemetryPipeline
from protocol import PACKET_SIZE, decode_packet

BUILD_DIR = Path(__file__).resolve().parents[2] / "transmitter" / "build"


def find_transmitter():
    candidates = [BUILD_DIR / "transmitter", BUILD_DIR / "transmitter.exe"]
    if os.getenv("TRANSMITTER_BIN"):
        candidates.insert(0, Path(os.environ["TRANSMITTER_BIN"]))
    return next((path for path in candidates if path.is_file()), None)


TRANSMITTER = find_transmitter()
pytestmark = pytest.mark.skipif(TRANSMITTER is None, reason="transmitter is not built")


def dump_packets(tmp_path, count, *extra_args):
    out = tmp_path / "flight.bin"
    subprocess.run(
        [str(TRANSMITTER), "--dump", str(out), "--count", str(count), "--seed", "1",
         *extra_args],
        check=True, timeout=60,
    )
    data = out.read_bytes()
    return [data[i:i + PACKET_SIZE] for i in range(0, len(data), PACKET_SIZE)]


def test_every_packet_from_the_encoder_decodes(tmp_path):
    packets = dump_packets(tmp_path, 300)

    assert len(packets) == 300
    assert all(len(packet) == PACKET_SIZE for packet in packets)

    readings = [decode_packet(packet) for packet in packets]
    assert [r["seq"] for r in readings] == list(range(300))
    assert [r["timestamp"] - readings[0]["timestamp"] for r in readings[:4]] == [0, 100, 200, 300]

    on_pad = readings[0]
    assert on_pad["flight_id"] == 1
    assert on_pad["imu_accel_z"] == pytest.approx(9.81, abs=0.5)
    assert on_pad["altitude_m"] == pytest.approx(0.0, abs=2.0)
    assert on_pad["gps_lat"] == pytest.approx(29.6516, abs=1e-3)
    assert on_pad["gps_lon"] == pytest.approx(-82.3248, abs=1e-3)
    assert on_pad["pressure_hpa"] == pytest.approx(1007.3, abs=1.0)


def test_without_a_launch_command_the_rocket_stays_on_the_pad(tmp_path):
    pipeline = TelemetryPipeline()
    results = [pipeline.process(packet) for packet in dump_packets(tmp_path, 600)]

    assert all(transition is None for _, transition in results)
    assert results[-1][0]["phase"] == "PAD"


def test_autolaunched_flight_goes_through_every_phase(tmp_path):
    pipeline = TelemetryPipeline()
    transitions = []
    for packet in dump_packets(tmp_path, 1000, "--autolaunch"):
        result = pipeline.process(packet)
        assert result is not None
        if result[1] is not None:
            transitions.append(result[1])

    first_flight = [t["to_phase"] for t in transitions if t["flight_id"] == 1]
    assert first_flight == ["POWERED_ASCENT", "COAST", "APOGEE", "DESCENT", "LANDED"]

    # After landing the simulator starts flight 2, which puts us back on the pad.
    second_flight = [t for t in transitions if t["flight_id"] == 2]
    assert second_flight[0]["from_phase"] == "LANDED"
    assert second_flight[0]["to_phase"] == "PAD"


def test_injected_faults_are_caught(tmp_path):
    pipeline = TelemetryPipeline()
    packets = dump_packets(tmp_path, 2000, "--autolaunch", "--corrupt", "0.05",
                           "--drop", "0.05", "--reorder", "0.05")

    accepted = [result[0]["seq"] for result in map(pipeline.process, packets) if result]

    stats = pipeline.stats()
    assert stats["corrupted"] > 0
    assert stats["lost"] > 0
    assert stats["out_of_order"] > 0
    assert accepted == sorted(set(accepted))
    assert stats["accepted"] == len(accepted)


class LiveTransmitter:
    """Runs the transmitter against a UDP socket owned by the test, with the
    flight sped up so a whole flight takes about a second."""

    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.settimeout(5)
        self.process = subprocess.Popen(
            [str(TRANSMITTER), "--port", str(self.socket.getsockname()[1]),
             "--seed", "1", "--speedup", "60"],
            stderr=subprocess.DEVNULL,
        )
        self.pipeline = TelemetryPipeline()
        self.address = None

    def close(self):
        self.process.kill()
        self.process.wait()
        self.socket.close()

    def read(self):
        """Receives one packet and returns (reading, transition) or None."""
        data, self.address = self.socket.recvfrom(1024)
        return self.pipeline.process(data)

    def send(self, command, spec=None):
        self.socket.sendto(encode_command(command, spec), self.address)

    def read_until(self, phase, limit=5000):
        """Reads until the detector reports `phase`; returns the transitions seen."""
        transitions = []
        for _ in range(limit):
            result = self.read()
            if result is None:
                continue
            reading, transition = result
            if transition is not None:
                transitions.append(transition)
            if reading["phase"] == phase:
                return transitions
        raise AssertionError(f"never reached {phase}; saw {transitions}")


@pytest.fixture
def transmitter():
    live = LiveTransmitter()
    yield live
    live.close()


def test_launch_command_over_udp_starts_a_flight(transmitter):
    for _ in range(20):
        reading, transition = transmitter.read()
        assert reading["phase"] == "PAD" and transition is None

    transmitter.send(COMMAND_LAUNCH, RocketSpec())
    transitions = transmitter.read_until("LANDED")

    assert [t["to_phase"] for t in transitions] == [
        "POWERED_ASCENT", "COAST", "APOGEE", "DESCENT", "LANDED"]
    assert 500 < transmitter.pipeline.summary()["peak_altitude_m"] < 800


def test_rocket_specs_in_the_command_change_the_flight(transmitter):
    transmitter.read()
    transmitter.send(COMMAND_LAUNCH, RocketSpec())
    transmitter.read_until("LANDED")
    default_peak = transmitter.pipeline.summary()["peak_altitude_m"]
    default_flight = transmitter.pipeline.flight_id

    # Twice the dry mass on the same motor: a new flight that peaks much lower.
    transmitter.send(COMMAND_LAUNCH, RocketSpec(dry_mass_kg=4.0))
    transmitter.read_until("PAD")
    transmitter.read_until("LANDED")

    assert transmitter.pipeline.flight_id == default_flight + 1
    assert transmitter.pipeline.summary()["peak_altitude_m"] < 0.6 * default_peak


def test_reset_command_abandons_the_flight(transmitter):
    transmitter.read()
    transmitter.send(COMMAND_LAUNCH, RocketSpec())
    transmitter.read_until("COAST")

    transmitter.send(COMMAND_RESET)
    transitions = transmitter.read_until("PAD")

    assert transitions[-1]["to_phase"] == "PAD"
    for _ in range(100):
        result = transmitter.read()
        assert result is None or result[0]["phase"] == "PAD"


def drain(transmitter, quiet_for=0.3):
    """Reads until the transmitter has been silent for `quiet_for` seconds."""
    transmitter.socket.settimeout(quiet_for)
    readings = []
    try:
        while True:
            result = transmitter.read()
            if result is not None:
                readings.append(result[0])
    except socket.timeout:
        return readings
    finally:
        transmitter.socket.settimeout(5)


def test_pause_freezes_the_flight_and_resume_carries_on(transmitter):
    transmitter.read()
    transmitter.send(COMMAND_LAUNCH, RocketSpec())
    transmitter.read_until("COAST")

    transmitter.send(COMMAND_PAUSE)
    before = drain(transmitter)[-1]
    assert drain(transmitter, quiet_for=0.5) == []  # silent while paused

    transmitter.send(COMMAND_RESUME)
    after, _ = transmitter.read()

    # The flight picks up exactly where it stopped: the next sequence number,
    # the next 100 ms of flight time, and still climbing from the same height.
    assert after["seq"] == before["seq"] + 1
    assert after["timestamp"] == before["timestamp"] + 100
    assert after["phase"] == "COAST"
    assert abs(after["altitude_m"] - before["altitude_m"]) < 20
    transmitter.read_until("LANDED")


def test_launch_while_paused_starts_a_new_flight(transmitter):
    transmitter.read()
    transmitter.send(COMMAND_LAUNCH, RocketSpec())
    transmitter.read_until("COAST")
    transmitter.send(COMMAND_PAUSE)
    drain(transmitter)

    transmitter.send(COMMAND_LAUNCH, RocketSpec())
    transmitter.read_until("PAD")

    assert transmitter.pipeline.flight_id == 2
    transmitter.read_until("LANDED")


def test_corrupted_command_is_ignored(transmitter):
    transmitter.read()
    command = bytearray(encode_command(COMMAND_LAUNCH, RocketSpec()))
    command[10] ^= 0x04
    transmitter.socket.sendto(bytes(command), transmitter.address)

    for _ in range(300):
        result = transmitter.read()
        assert result is None or result[0]["phase"] == "PAD"
