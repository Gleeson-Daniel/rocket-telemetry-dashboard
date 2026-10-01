"""A small flight model for tests, independent of the C++ transmitter."""
import random

G = 9.81
DT = 0.1
BURN_TIME_S = 2.5
THRUST_ACCEL = 60.0
BODY_DRAG = 0.0006
CHUTE_DRAG = G / 18.0 ** 2

ORDERED_PHASES = ["PAD", "POWERED_ASCENT", "COAST", "APOGEE", "DESCENT", "LANDED"]


def simulate_flight(seed=0, altitude_noise=0.4, accel_noise=0.08,
                    pad_s=3.0, landed_s=4.0):
    """Returns one flight as a list of readings sampled at 10 Hz.

    Each reading also carries `true_altitude` and `stage` so tests can
    compare what the detector decided against what really happened.
    """
    rng = random.Random(seed)
    readings = []
    stage, stage_time = "pad", 0.0
    altitude = velocity = 0.0
    timestamp = 1_700_000_000_000

    while not (stage == "landed" and stage_time >= landed_s):
        for _ in range(10):
            dt = DT / 10
            stage_time += dt
            if stage == "pad":
                force = G
                if stage_time >= pad_s:
                    stage, stage_time = "boost", 0.0
                continue
            if stage == "landed":
                force = G
                continue
            thrust = THRUST_ACCEL if stage == "boost" else 0.0
            drag_k = CHUTE_DRAG if stage == "descent" else BODY_DRAG
            force = thrust - drag_k * velocity * abs(velocity)
            velocity += (force - G) * dt
            altitude += velocity * dt
            if stage == "boost" and stage_time >= BURN_TIME_S:
                stage, stage_time = "coast", 0.0
            elif stage == "coast" and velocity <= 0:
                stage, stage_time = "descent", 0.0
            elif stage == "descent" and altitude <= 0:
                altitude = velocity = 0.0
                force = G
                stage, stage_time = "landed", 0.0

        timestamp += 100
        readings.append({
            "timestamp": timestamp,
            "imu_accel_z": force + rng.gauss(0, accel_noise),
            "altitude_m": altitude + rng.gauss(0, altitude_noise),
            "true_altitude": altitude,
            "stage": stage,
        })
    return readings


def run_detector(detector, readings):
    """Feeds readings through a detector and returns the transitions it made."""
    transitions = []
    for reading in readings:
        transition = detector.update(reading)
        if transition is not None:
            transitions.append(transition)
    return transitions
