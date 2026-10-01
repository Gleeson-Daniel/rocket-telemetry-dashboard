"""Reads a flight log from a CSV file and turns it into 10 Hz readings."""
import csv
import math
import re
from dataclasses import dataclass
from statistics import median

SAMPLE_RATE_HZ = 10
G = 9.81
MAX_DURATION_S = 30 * 60
MIN_DURATION_S = 2.0

CHANNELS = (
    "imu_accel_x", "imu_accel_y", "imu_accel_z",
    "imu_gyro_x", "imu_gyro_y", "imu_gyro_z",
    "pressure_hpa", "altitude_m", "gps_lat", "gps_lon",
    "temperature_c", "battery_v",
)

# (field, pattern for the cleaned-up column name, multiplier to our units).
# A column name is cleaned up by lower-casing it and turning every run of
# punctuation or spaces into one underscore, so "Altitude (ft)" is altitude_ft.
_ACCEL_Z = r"(imu_)?(accel|acceleration|accel_z|acceleration_z|az|axial_accel)"
_ALTITUDE = r"(altitude|alt|height)(_agl|_baro)?"
_COLUMNS = [
    ("time", r"(flight_)?(time|t|timestamp)(_s|_sec|_seconds)?|seconds", 1.0),
    ("time", r"(flight_)?(time|t|timestamp)_(ms|millis|milliseconds)", 0.001),
    ("altitude_m", _ALTITUDE + r"(_m|_meters|_metres)?", 1.0),
    ("altitude_m", _ALTITUDE + r"_(ft|feet)", 0.3048),
    ("imu_accel_z", _ACCEL_Z + r"(_ms2|_m_s2|_m_s_2|_mps2)?", 1.0),
    ("imu_accel_z", _ACCEL_Z + r"_(g|gs)", 9.80665),
    ("imu_accel_x", r"(imu_)?(accel_x|ax)", 1.0),
    ("imu_accel_y", r"(imu_)?(accel_y|ay)", 1.0),
    ("imu_gyro_x", r"(imu_)?(gyro_x|gx)", 1.0),
    ("imu_gyro_y", r"(imu_)?(gyro_y|gy)", 1.0),
    ("imu_gyro_z", r"(imu_)?(gyro_z|gz)", 1.0),
    ("pressure_hpa", r"pressure(_hpa|_mbar)?", 1.0),
    ("pressure_hpa", r"pressure_pa", 0.01),
    ("temperature_c", r"(temperature|temp)(_c|_degc)?", 1.0),
    ("battery_v", r"(battery|voltage|battery_voltage|vbat)(_v)?", 1.0),
    ("gps_lat", r"(gps_)?(lat|latitude)", 1.0),
    ("gps_lon", r"(gps_)?(lon|lng|long|longitude)", 1.0),
]


class FlightLogError(ValueError):
    """The file can't be used as a flight log. The message is for the user."""


@dataclass
class FlightLog:
    readings: list  # one dict of all channels per 0.1 s
    missing: list   # channels the log didn't have; they are 0.0 in readings
    info: dict


def _identify(header: str):
    name = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")
    for field, pattern, scale in _COLUMNS:
        if re.fullmatch(pattern, name):
            return field, scale
    return None


def _number(cell: str):
    try:
        value = float(cell)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _read_rows(text: str):
    """Returns (times, {field: values}) for the columns we recognise."""
    lines = [line for line in text.lstrip("﻿").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        raise FlightLogError("The file is empty.")

    delimiter = max(",;\t", key=lines[0].count)
    rows = csv.reader(lines, delimiter=delimiter)
    header = [cell.strip() for cell in next(rows)]

    columns = {}
    for index, name in enumerate(header):
        match = _identify(name)
        if match and match[0] not in columns:
            columns[match[0]] = (index, match[1])

    if "time" not in columns or "altitude_m" not in columns:
        raise FlightLogError(
            "The first row must name the columns, and there must be a time "
            "column and an altitude column. Found: " + ", ".join(header) + "."
        )

    optional = [field for field in columns if field not in ("time", "altitude_m")]
    samples = []
    previous = {field: 0.0 for field in optional}
    for row in rows:
        def cell(field):
            index, scale = columns[field]
            value = _number(row[index].strip()) if index < len(row) else None
            return None if value is None else value * scale

        time, altitude = cell("time"), cell("altitude_m")
        if time is None or altitude is None:
            continue
        # A blank in an optional column repeats the last good value.
        for field in optional:
            value = cell(field)
            previous[field] = previous[field] if value is None else value
        samples.append((time, {"altitude_m": altitude, **previous}))

    samples.sort(key=lambda sample: sample[0])
    times, values = [], {field: [] for field in ["altitude_m"] + optional}
    for time, sample in samples:
        if times and time <= times[-1]:
            continue  # repeated timestamp
        times.append(time)
        for field in values:
            values[field].append(sample[field])
    return times, values


def _resample(times, values, count):
    """Linear interpolation onto an even 10 Hz grid starting at times[0]."""
    result = []
    j = 0
    for i in range(count):
        t = times[0] + i / SAMPLE_RATE_HZ
        while j < len(times) - 2 and times[j + 1] < t:
            j += 1
        span = times[j + 1] - times[j]
        weight = min(max((t - times[j]) / span, 0.0), 1.0)
        result.append(values[j] + weight * (values[j + 1] - values[j]))
    return result


def _slope(values, reach=3):
    """Rate of change per second, measured across `reach` samples each side."""
    last = len(values) - 1
    result = []
    for i in range(len(values)):
        lo, hi = max(i - reach, 0), min(i + reach, last)
        result.append((values[hi] - values[lo]) * SAMPLE_RATE_HZ / (hi - lo))
    return result


def parse_flight_log(text: str) -> FlightLog:
    times, columns = _read_rows(text)
    if len(times) < 10:
        raise FlightLogError(f"Only {len(times)} usable rows; need at least 10.")
    duration = times[-1] - times[0]
    if duration < MIN_DURATION_S:
        raise FlightLogError(
            f"The log covers {duration:.2f} s. Check that the time column is in seconds."
        )
    if duration > MAX_DURATION_S:
        raise FlightLogError(
            f"The log covers {duration / 60:.0f} minutes; the limit is "
            f"{MAX_DURATION_S // 60}. Check that the time column is in seconds."
        )

    count = int(duration * SAMPLE_RATE_HZ) + 1
    channels = {field: _resample(times, values, count) for field, values in columns.items()}

    # The phase detector expects height above the pad, and many altimeters
    # log height above sea level, so zero it on the first second of the log.
    ground = median(channels["altitude_m"][:SAMPLE_RATE_HZ])
    channels["altitude_m"] = [altitude - ground for altitude in channels["altitude_m"]]

    if "imu_accel_z" in channels:
        accel_source = "log"
        # An accelerometer at rest reads +1 g. A log that reads about zero at
        # rest has had gravity taken out, so put it back.
        if abs(median(channels["imu_accel_z"][:SAMPLE_RATE_HZ])) < 3.0:
            channels["imu_accel_z"] = [accel + G for accel in channels["imu_accel_z"]]
            accel_source = "log, with gravity added back"
    else:
        accel_source = "derived from altitude"
        channels["imu_accel_z"] = [accel + G for accel in _slope(_slope(channels["altitude_m"]))]

    missing = [channel for channel in CHANNELS if channel not in channels]
    readings = [
        {channel: channels[channel][i] if channel in channels else 0.0 for channel in CHANNELS}
        for i in range(count)
    ]
    info = {
        "samples": count,
        "duration_s": round(duration, 1),
        "peak_altitude_m": round(max(channels["altitude_m"]), 1),
        "accel_source": accel_source,
        "missing": missing,
    }
    return FlightLog(readings, missing, info)
