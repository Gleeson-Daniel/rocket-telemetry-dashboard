import pytest

from flight_profile import ORDERED_PHASES, simulate_flight
from pipeline import TelemetryPipeline
from protocol import encode_packet


def packets_for(flight, flight_id=1, first_seq=0):
    packets = []
    for offset, reading in enumerate(flight):
        packets.append(encode_packet({
            "flight_id": flight_id,
            "seq": first_seq + offset,
            "timestamp": reading["timestamp"],
            "imu_accel_x": 0.0, "imu_accel_y": 0.0,
            "imu_accel_z": reading["imu_accel_z"],
            "imu_gyro_x": 0.0, "imu_gyro_y": 0.0, "imu_gyro_z": 0.0,
            "pressure_hpa": 1013.25,
            "altitude_m": reading["altitude_m"],
            "gps_lat": 29.6516, "gps_lon": -82.3248,
            "temperature_c": 25.0,
            "battery_v": 4.2,
        }))
    return packets


def feed(pipeline, packets):
    results = [pipeline.process(packet) for packet in packets]
    return [result for result in results if result is not None]


def test_good_packets_come_out_tagged_with_a_phase():
    pipeline = TelemetryPipeline()
    results = feed(pipeline, packets_for(simulate_flight(seed=0)))

    transitions = [transition for _, transition in results if transition]
    assert ["PAD"] + [t["to_phase"] for t in transitions] == ORDERED_PHASES
    assert all(t["flight_id"] == 1 for t in transitions)
    assert results[0][0]["phase"] == "PAD"
    assert results[-1][0]["phase"] == "LANDED"


def test_corrupted_packet_is_dropped_and_counted():
    pipeline = TelemetryPipeline()
    packets = packets_for(simulate_flight(seed=0)[:10])
    corrupted = bytearray(packets[4])
    corrupted[20] ^= 0x10
    packets[4] = bytes(corrupted)

    results = feed(pipeline, packets)

    assert [reading["seq"] for reading, _ in results] == [0, 1, 2, 3, 5, 6, 7, 8, 9]
    assert pipeline.stats() == {
        "received": 10, "accepted": 9, "corrupted": 1, "lost": 1, "out_of_order": 0,
    }


def test_out_of_order_packet_is_dropped_and_counted():
    pipeline = TelemetryPipeline()
    packets = packets_for(simulate_flight(seed=0)[:6])
    packets[2], packets[3] = packets[3], packets[2]

    results = feed(pipeline, packets)

    assert [reading["seq"] for reading, _ in results] == [0, 1, 3, 4, 5]
    assert pipeline.stats()["out_of_order"] == 1


def test_garbage_datagram_is_ignored():
    pipeline = TelemetryPipeline()

    assert pipeline.process(b"not a telemetry packet") is None
    assert pipeline.stats()["corrupted"] == 1


def test_summary_tracks_the_flight_from_launch_to_landing():
    pipeline = TelemetryPipeline()
    flight = simulate_flight(seed=0, pad_s=3.0, landed_s=4.0)
    assert pipeline.summary() == {
        "peak_altitude_m": 0.0, "max_accel_ms2": 0.0, "flight_time_s": 0.0}

    feed(pipeline, packets_for(flight))

    summary = pipeline.summary()
    true_peak = max(r["true_altitude"] for r in flight)
    assert summary["peak_altitude_m"] == pytest.approx(true_peak, abs=2.0)
    assert 40 < summary["max_accel_ms2"] < 65
    # The flight is 3 s of pad at the start and 4 s on the ground at the end;
    # the clock must stop at landing instead of running on.
    airborne_s = len(flight) / 10 - 3.0 - 4.0
    assert summary["flight_time_s"] == pytest.approx(airborne_s, abs=2.0)


def test_summary_starts_again_for_a_new_flight():
    pipeline = TelemetryPipeline()
    first = simulate_flight(seed=0)
    feed(pipeline, packets_for(first, flight_id=1))

    pipeline.process(packets_for(simulate_flight(seed=1), flight_id=2, first_seq=len(first))[0])

    assert pipeline.summary()["peak_altitude_m"] == 0.0
    assert pipeline.summary()["flight_time_s"] == 0.0


def test_new_flight_id_resets_the_phase_to_pad():
    pipeline = TelemetryPipeline()
    first = simulate_flight(seed=0)
    feed(pipeline, packets_for(first, flight_id=1))
    assert pipeline.detector.phase.value == "LANDED"

    second = packets_for(simulate_flight(seed=1), flight_id=2, first_seq=len(first))
    reading, transition = pipeline.process(second[0])

    assert reading["phase"] == "PAD"
    assert transition["from_phase"] == "LANDED"
    assert transition["to_phase"] == "PAD"
    assert transition["flight_id"] == 2
