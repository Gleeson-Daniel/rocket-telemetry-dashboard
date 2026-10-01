from pathlib import Path

import pytest

from flight_profile import ORDERED_PHASES, run_detector, simulate_flight
from phase_detector import PhaseDetector
from replay import CHANNELS, FlightLogError, parse_flight_log

SAMPLE_LOG = Path(__file__).resolve().parents[2] / "samples" / "sample_flight.csv"


def to_csv(header, rows):
    return "\n".join([header] + [",".join(str(cell) for cell in row) for row in rows])


def flight_rows(seed=0, every=1):
    """(seconds, altitude, accel) rows from the test flight model."""
    flight = simulate_flight(seed=seed)
    return [(i / 10, r["altitude_m"], r["imu_accel_z"]) for i, r in enumerate(flight)][::every]


def phases_for(log):
    readings = [dict(reading, timestamp=i * 100) for i, reading in enumerate(log.readings)]
    return ["PAD"] + [t["to_phase"] for t in run_detector(PhaseDetector(), readings)]


def test_basic_log_is_read():
    rows = flight_rows()
    log = parse_flight_log(to_csv("time_s,altitude_m,accel_z", rows))

    assert log.info["samples"] == len(rows)
    assert log.info["accel_source"] == "log"
    assert set(log.readings[0]) == set(CHANNELS)
    assert phases_for(log) == ORDERED_PHASES


def test_channels_the_log_lacks_are_reported_as_missing():
    log = parse_flight_log(to_csv("time,altitude,accel", flight_rows()))

    assert "battery_v" in log.missing
    assert "gps_lat" in log.missing
    assert "altitude_m" not in log.missing
    assert "imu_accel_z" not in log.missing


def test_acceleration_is_derived_when_the_log_has_only_altitude():
    rows = [(t, altitude) for t, altitude, _ in flight_rows()]
    log = parse_flight_log(to_csv("time,altitude", rows))

    assert log.info["accel_source"] == "derived from altitude"
    assert "imu_accel_z" not in log.missing
    assert phases_for(log) == ORDERED_PHASES
    on_pad = [reading["imu_accel_z"] for reading in log.readings[5:20]]
    assert sum(on_pad) / len(on_pad) == pytest.approx(9.81, abs=3.0)


def test_feet_and_g_are_converted():
    rows = [(t, altitude / 0.3048, accel / 9.80665) for t, altitude, accel in flight_rows()]
    metric = parse_flight_log(to_csv("time_s,altitude_m,accel_z", flight_rows()))
    imperial = parse_flight_log(to_csv("Time (s),Altitude (ft),Accel (g)", rows))

    assert imperial.info["peak_altitude_m"] == pytest.approx(metric.info["peak_altitude_m"], abs=0.1)
    assert imperial.readings[40]["imu_accel_z"] == pytest.approx(
        metric.readings[40]["imu_accel_z"], abs=0.01)


def test_milliseconds_are_converted():
    rows = [(round(t * 1000), altitude, accel) for t, altitude, accel in flight_rows()]
    log = parse_flight_log(to_csv("time_ms,altitude,accel", rows))

    assert log.info["duration_s"] == pytest.approx(flight_rows()[-1][0], abs=0.1)


@pytest.mark.parametrize("every", [2, 3])
def test_slower_logs_are_resampled_to_10_hz(every):
    rows = flight_rows(every=every)
    log = parse_flight_log(to_csv("time,altitude,accel", rows))

    assert log.info["samples"] == int(rows[-1][0] * 10) + 1
    assert phases_for(log) == ORDERED_PHASES


def test_faster_logs_are_resampled_to_10_hz():
    # Stretch the 10 Hz flight to 50 Hz by repeating each row five times.
    rows = [(i / 50, altitude, accel)
            for i, (_, altitude, accel) in enumerate(
                row for row in flight_rows() for _ in range(5))]
    log = parse_flight_log(to_csv("time,altitude,accel", rows))

    assert log.info["samples"] == int(rows[-1][0] * 10) + 1
    assert phases_for(log) == ORDERED_PHASES


def test_altitude_above_sea_level_is_zeroed_on_the_pad():
    rows = [(t, altitude + 1400.0, accel) for t, altitude, accel in flight_rows()]
    log = parse_flight_log(to_csv("time,altitude,accel", rows))

    assert abs(log.readings[0]["altitude_m"]) < 2.0
    assert phases_for(log) == ORDERED_PHASES


def test_acceleration_logged_without_gravity_gets_it_back():
    rows = [(t, altitude, accel - 9.81) for t, altitude, accel in flight_rows()]
    log = parse_flight_log(to_csv("time,altitude,accel", rows))

    assert log.info["accel_source"] == "log, with gravity added back"
    assert log.readings[5]["imu_accel_z"] == pytest.approx(9.81, abs=0.5)
    assert phases_for(log) == ORDERED_PHASES


def test_semicolons_comments_and_blank_lines_are_tolerated():
    rows = flight_rows()
    body = "\n".join(f"{t};{altitude};{accel}" for t, altitude, accel in rows)
    text = "# exported by some altimeter\n\ntime;altitude;accel\n" + body + "\n\n"

    assert parse_flight_log(text).info["samples"] == len(rows)


def test_unusable_rows_are_skipped():
    rows = flight_rows()
    rows[10] = ("oops", 1.0, 9.81)
    rows[11] = (1.1, "", 9.81)
    rows[12] = (1.2, "nan", 9.81)

    log = parse_flight_log(to_csv("time,altitude,accel", rows))

    assert phases_for(log) == ORDERED_PHASES


@pytest.mark.parametrize("text,message", [
    ("", "empty"),
    ("# only a comment\n", "empty"),
    ("time,speed\n0,1\n1,2\n", "altitude column"),
    ("0,0\n1,5\n2,9\n", "altitude column"),
    ("time,altitude\n0,0\n1,5\n", "need at least 10"),
    (to_csv("time,altitude", [(i / 1000, i) for i in range(50)]), "seconds"),
    (to_csv("time,altitude", [(i * 1000, i) for i in range(50)]), "minutes"),
])
def test_unusable_files_explain_what_is_wrong(text, message):
    with pytest.raises(FlightLogError, match=message):
        parse_flight_log(text)


def test_sample_log_in_the_repository_replays_cleanly():
    log = parse_flight_log(SAMPLE_LOG.read_text())

    assert phases_for(log) == ORDERED_PHASES
    assert 500 < log.info["peak_altitude_m"] < 800
    assert log.info["accel_source"] == "log"
    assert "pressure_hpa" not in log.missing
    assert "battery_v" in log.missing
