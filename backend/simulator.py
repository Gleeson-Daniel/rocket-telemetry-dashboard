import numpy as np
import time
from dataclasses import dataclass, asdict

@dataclass
class SensorReading:
    timestamp: float
    imu_accel_x: float
    imu_accel_y: float
    imu_accel_z: float
    imu_gyro_x: float
    imu_gyro_y: float
    imu_gyro_z: float
    pressure_hpa: float
    altitude_m: float
    gps_lat: float
    gps_lon: float
    temperature_c: float
    battery_v: float

class SensorSimulator:
    def __init__(self):
        self.t = 0.0
        self.base_alt = 100.0
        self.lat = 29.6516
        self.lon = -82.3248

    def next(self) -> dict:
        self.t += 0.1
        alt = self.base_alt + 30 * np.sin(self.t * 0.3) + np.random.normal(0, 0.4)
        reading = SensorReading(
            timestamp=round(time.time() * 1000),
            imu_accel_x=round(np.random.normal(0.0, 0.15), 4),
            imu_accel_y=round(np.random.normal(0.0, 0.15), 4),
            imu_accel_z=round(np.random.normal(-9.81, 0.08), 4),
            imu_gyro_x=round(np.random.normal(0.0, 0.03), 4),
            imu_gyro_y=round(np.random.normal(0.0, 0.03), 4),
            imu_gyro_z=round(np.random.normal(0.0, 0.03), 4),
            pressure_hpa=round(1013.25 - alt * 0.12 + np.random.normal(0, 0.1), 2),
            altitude_m=round(alt, 2),
            gps_lat=round(self.lat + self.t * 0.00002, 6),
            gps_lon=round(self.lon + np.sin(self.t * 0.15) * 0.0002, 6),
            temperature_c=round(25.0 - alt * 0.0065 + np.random.normal(0, 0.3), 2),
            battery_v=round(max(3.2, 4.2 - self.t * 0.0008 + np.random.normal(0, 0.005)), 3)
        )
        return asdict(reading)