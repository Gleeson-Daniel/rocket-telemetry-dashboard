import random

import pytest

from flight_profile import ORDERED_PHASES, run_detector, simulate_flight
from phase_detector import FlightPhase, PhaseDetector


def phases_visited(transitions):
    return ["PAD"] + [t["to_phase"] for t in transitions]


def pad_reading(accel=9.81, altitude=0.0, timestamp=0):
    return {"timestamp": timestamp, "imu_accel_z": accel, "altitude_m": altitude}


@pytest.mark.parametrize("seed", range(25))
def test_nominal_flight_visits_every_phase_in_order(seed):
    detector = PhaseDetector()
    transitions = run_detector(detector, simulate_flight(seed=seed))

    assert phases_visited(transitions) == ORDERED_PHASES
    assert detector.phase is FlightPhase.LANDED


@pytest.mark.parametrize("seed", range(10))
def test_apogee_is_called_close_to_the_true_peak(seed):
    flight = simulate_flight(seed=seed)
    transitions = run_detector(PhaseDetector(), flight)

    true_peak = max(flight, key=lambda r: r["true_altitude"])
    apogee = next(t for t in transitions if t["to_phase"] == "APOGEE")

    seconds_late = (apogee["timestamp"] - true_peak["timestamp"]) / 1000
    assert 0 <= seconds_late <= 2.0
    assert true_peak["true_altitude"] - apogee["altitude_m"] < 10.0


@pytest.mark.parametrize("seed", range(25))
def test_noisy_readings_around_apogee_do_not_flap(seed):
    # Altitude noise of 1.5 m is far larger than how much the true altitude
    # changes from one sample to the next near the top of the flight.
    flight = simulate_flight(seed=seed, altitude_noise=1.5)
    transitions = run_detector(PhaseDetector(), flight)

    assert phases_visited(transitions) == ORDERED_PHASES

    true_peak = max(flight, key=lambda r: r["true_altitude"])
    apogee = next(t for t in transitions if t["to_phase"] == "APOGEE")
    assert abs(apogee["timestamp"] - true_peak["timestamp"]) <= 3000


@pytest.mark.parametrize("spike_length,expect_launch", [(1, False), (2, False), (3, True)])
def test_launch_needs_sustained_acceleration(spike_length, expect_launch):
    detector = PhaseDetector()
    readings = ([pad_reading()] * 20 + [pad_reading(accel=80.0)] * spike_length
                + [pad_reading()] * 20)
    run_detector(detector, readings)

    launched = detector.phase is not FlightPhase.PAD
    assert launched == expect_launch


def test_single_altitude_glitch_on_the_pad_is_ignored():
    detector = PhaseDetector()
    readings = [pad_reading()] * 20 + [pad_reading(altitude=5000.0)] + [pad_reading()] * 20

    assert run_detector(detector, readings) == []
    assert detector.phase is FlightPhase.PAD


@pytest.mark.parametrize("glitch", [-300.0, 300.0])
def test_single_altitude_glitch_during_coast_does_not_trigger_apogee(glitch):
    flight = simulate_flight(seed=3)
    coast = [i for i, r in enumerate(flight) if r["stage"] == "coast"]
    glitch_at = coast[len(coast) // 3]
    flight[glitch_at] = dict(flight[glitch_at],
                             altitude_m=flight[glitch_at]["altitude_m"] + glitch)

    transitions = run_detector(PhaseDetector(), flight)

    assert phases_visited(transitions) == ORDERED_PHASES
    true_peak = max(flight, key=lambda r: r["true_altitude"])
    apogee = next(t for t in transitions if t["to_phase"] == "APOGEE")
    assert 0 <= apogee["timestamp"] - true_peak["timestamp"] <= 2000


@pytest.mark.parametrize("seed", range(10))
def test_dropped_packets_do_not_break_the_sequence(seed):
    rng = random.Random(seed)
    flight = [r for r in simulate_flight(seed=seed) if rng.random() > 0.2]

    transitions = run_detector(PhaseDetector(), flight)

    assert phases_visited(transitions) == ORDERED_PHASES


def test_joining_mid_flight_picks_up_from_coast():
    flight = simulate_flight(seed=1)
    first_coast = next(i for i, r in enumerate(flight) if r["stage"] == "coast")
    detector = PhaseDetector()

    transitions = run_detector(detector, flight[first_coast + 10:])

    assert phases_visited(transitions) == ["PAD", "COAST", "APOGEE", "DESCENT", "LANDED"]


def test_slow_motion_at_apogee_is_not_mistaken_for_landing():
    flight = simulate_flight(seed=2)
    transitions = run_detector(PhaseDetector(), flight)
    landed = next(t for t in transitions if t["to_phase"] == "LANDED")

    assert landed["altitude_m"] < 5.0


def test_reset_returns_to_pad():
    detector = PhaseDetector()
    run_detector(detector, simulate_flight(seed=0))
    assert detector.phase is FlightPhase.LANDED

    detector.reset()

    assert detector.phase is FlightPhase.PAD
    assert phases_visited(run_detector(detector, simulate_flight(seed=4))) == ORDERED_PHASES
