from phase_detector import FlightPhase, PhaseDetector
from protocol import PacketError, SequenceTracker, decode_packet


class TelemetryPipeline:
    """Turns raw datagrams into validated readings tagged with a flight phase."""

    def __init__(self):
        self.sequence = SequenceTracker()
        self.detector = PhaseDetector()
        self.flight_id = None
        self.received = 0
        self.accepted = 0
        self.corrupted = 0
        self._start_flight()

    def _start_flight(self):
        self.detector.reset()
        self._launched_at = None
        self._max_accel = 0.0
        self._flight_time = 0.0

    def process(self, datagram: bytes):
        """Returns (reading, transition) for a good packet, or None if dropped.

        `transition` is None unless this reading changed the flight phase.
        """
        self.received += 1
        try:
            reading = decode_packet(datagram)
        except PacketError:
            self.corrupted += 1
            return None

        if not self.sequence.accept(reading["seq"]):
            return None
        self.accepted += 1

        transition = None
        if reading["flight_id"] != self.flight_id:
            # A new flight id means the rocket is back on the pad.
            if self.flight_id is not None and self.detector.phase is not FlightPhase.PAD:
                transition = {
                    "timestamp": reading["timestamp"],
                    "from_phase": self.detector.phase.value,
                    "to_phase": FlightPhase.PAD.value,
                    "altitude_m": reading["altitude_m"],
                }
            self._start_flight()
            self.flight_id = reading["flight_id"]

        was_on_pad = self.detector.phase is FlightPhase.PAD
        transition = self.detector.update(reading) or transition
        if transition is not None:
            transition["flight_id"] = reading["flight_id"]

        phase = self.detector.phase
        if was_on_pad and phase is not FlightPhase.PAD:
            self._launched_at = reading["timestamp"]
        if self._launched_at is not None and phase is not FlightPhase.LANDED:
            self._flight_time = (reading["timestamp"] - self._launched_at) / 1000
            self._max_accel = max(self._max_accel, reading["imu_accel_z"])

        reading["phase"] = phase.value
        return reading, transition

    def summary(self) -> dict:
        """Headline numbers for the current flight, from launch to landing."""
        return {
            "peak_altitude_m": round(self.detector.peak_altitude, 1),
            "max_accel_ms2": round(self._max_accel, 1),
            "flight_time_s": round(self._flight_time, 1),
        }

    def stats(self) -> dict:
        return {
            "received": self.received,
            "accepted": self.accepted,
            "corrupted": self.corrupted,
            "lost": self.sequence.lost,
            "out_of_order": self.sequence.out_of_order,
        }
