from collections import deque
from enum import Enum
from statistics import median


class FlightPhase(str, Enum):
    PAD = "PAD"
    POWERED_ASCENT = "POWERED_ASCENT"
    COAST = "COAST"
    APOGEE = "APOGEE"
    DESCENT = "DESCENT"
    LANDED = "LANDED"


class PhaseDetector:
    """Works out the flight phase from accelerometer and altitude readings.

    Two things keep sensor noise from flipping the phase:
      - altitude is smoothed with a median over the last few samples, which
        throws away a single wild reading completely;
      - every transition needs its condition to hold for several samples in
        a row, so one reading over a threshold is never enough.

    Acceleration is specific force along the rocket's long axis: about +9.81
    at rest, large and positive under thrust, near zero in free fall.
    Altitude is metres above the pad. Sample counts assume roughly 10 Hz.
    """

    LAUNCH_ACCEL = 20.0         # m/s^2, about 2 g: the motor has lit
    BURNOUT_ACCEL = 5.0         # m/s^2, below this thrust has stopped
    AIRBORNE_ALTITUDE_M = 30.0  # clearly off the pad
    APOGEE_DROP_M = 2.0         # this far below the peak means past the top
    DESCENT_DROP_M = 10.0       # this far below the peak means falling
    LANDED_RANGE_M = 3.0        # under a parachute it changes far more per second

    CONFIRM_SAMPLES = 3
    LANDED_CONFIRM_SAMPLES = 10
    SMOOTHING_WINDOW = 5
    RATE_WINDOW = 10

    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = FlightPhase.PAD
        self.peak_altitude = 0.0
        self._recent = deque(maxlen=self.SMOOTHING_WINDOW)
        self._smoothed = deque(maxlen=self.RATE_WINDOW + 1)
        self._streaks = {}

    def update(self, reading: dict):
        """Feed one reading. Returns a transition dict if the phase changed."""
        accel = reading["imu_accel_z"]
        self._recent.append(reading["altitude_m"])
        altitude = median(self._recent)
        self._smoothed.append(altitude)

        if self.phase is not FlightPhase.PAD:
            self.peak_altitude = max(self.peak_altitude, altitude)
        below_peak = self.peak_altitude - altitude

        next_phase = None
        if self.phase is FlightPhase.PAD:
            if self._held("launch", accel > self.LAUNCH_ACCEL):
                next_phase = FlightPhase.POWERED_ASCENT
            # If the ground station starts listening mid-flight it never sees
            # the launch, so being well off the ground counts as flying too.
            elif self._held("airborne", altitude > self.AIRBORNE_ALTITUDE_M):
                next_phase = FlightPhase.COAST
        elif self.phase is FlightPhase.POWERED_ASCENT:
            if self._held("burnout", accel < self.BURNOUT_ACCEL):
                next_phase = FlightPhase.COAST
        elif self.phase is FlightPhase.COAST:
            if self._held("apogee", below_peak > self.APOGEE_DROP_M):
                next_phase = FlightPhase.APOGEE
        elif self.phase is FlightPhase.APOGEE:
            if self._held("descent", below_peak > self.DESCENT_DROP_M):
                next_phase = FlightPhase.DESCENT
        elif self.phase is FlightPhase.DESCENT:
            at_rest = (len(self._smoothed) == self._smoothed.maxlen and
                       abs(altitude - self._smoothed[0]) < self.LANDED_RANGE_M)
            if self._held("landed", at_rest, self.LANDED_CONFIRM_SAMPLES):
                next_phase = FlightPhase.LANDED

        if next_phase is None:
            return None

        transition = {
            "timestamp": reading["timestamp"],
            "from_phase": self.phase.value,
            "to_phase": next_phase.value,
            "altitude_m": round(altitude, 2),
        }
        self.phase = next_phase
        self._streaks = {}
        if next_phase in (FlightPhase.POWERED_ASCENT, FlightPhase.COAST):
            self.peak_altitude = max(self.peak_altitude, altitude)
        return transition

    def _held(self, name: str, condition: bool, samples: int = CONFIRM_SAMPLES) -> bool:
        """True once `condition` has been true for `samples` readings in a row."""
        self._streaks[name] = self._streaks.get(name, 0) + 1 if condition else 0
        return self._streaks[name] >= samples
