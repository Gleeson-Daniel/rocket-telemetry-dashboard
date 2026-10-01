#include "flight_sim.hpp"

#include <algorithm>
#include <cmath>

namespace telemetry {
namespace {

constexpr double G = 9.81;
constexpr double PI = 3.14159265358979323846;

constexpr double AUTOLAUNCH_PAD_HOLD_S = 8.0;
constexpr double AUTOLAUNCH_LANDED_HOLD_S = 8.0;
constexpr double COMMANDED_PAD_HOLD_S = 1.0;  // ignition delay after a launch command
constexpr double ROLL_RATE = 2.0;             // rad/s spin during ascent

constexpr double SEA_LEVEL_AIR_DENSITY = 1.225;  // kg/m^3
constexpr double DENSITY_SCALE_HEIGHT_M = 8500.0;

constexpr double WIND_EAST = 4.0;   // m/s
constexpr double WIND_NORTH = 1.5;  // m/s

constexpr double PAD_LAT = 29.6516;
constexpr double PAD_LON = -82.3248;
constexpr double PAD_ELEVATION_M = 50.0;
constexpr double METERS_PER_DEGREE = 111320.0;

constexpr int SUBSTEPS = 10;

// Standard-atmosphere pressure at a height above mean sea level.
double pressure_hpa(double altitude_msl) {
    return 1013.25 * std::pow(1.0 - 2.25577e-5 * altitude_msl, 5.25588);
}

double air_density(double altitude_msl) {
    return SEA_LEVEL_AIR_DENSITY * std::exp(-altitude_msl / DENSITY_SCALE_HEIGHT_M);
}

double disc_area(double diameter) {
    return PI * diameter * diameter / 4.0;
}

}  // namespace

bool RocketConfig::valid() const {
    const double values[] = {dry_mass_kg, propellant_mass_kg, thrust_n, burn_time_s,
                             diameter_m, drag_coefficient, chute_diameter_m,
                             chute_drag_coefficient};
    return std::all_of(std::begin(values), std::end(values),
                       [](double v) { return std::isfinite(v) && v > 0.0; });
}

FlightSimulator::FlightSimulator(std::uint32_t seed, bool autolaunch)
    : rng_(seed),
      autolaunch_(autolaunch),
      armed_(autolaunch),
      pad_hold_(AUTOLAUNCH_PAD_HOLD_S),
      specific_force_(G) {}

double FlightSimulator::noise(double sigma) {
    return std::normal_distribution<double>(0.0, sigma)(rng_);
}

void FlightSimulator::enter(Stage stage) {
    stage_ = stage;
    stage_time_ = 0.0;
}

void FlightSimulator::start_new_flight() {
    enter(Stage::Pad);
    armed_ = false;
    altitude_ = 0.0;
    velocity_ = 0.0;
    specific_force_ = G;
    east_ = 0.0;
    north_ = 0.0;
    // Flight id 0 is reserved for replayed logs on the ground station.
    flight_id_ = flight_id_ == 255 ? 1 : static_cast<std::uint8_t>(flight_id_ + 1);
}

bool FlightSimulator::launch(const RocketConfig& config) {
    if (!config.valid()) return false;
    if (stage_ != Stage::Pad) start_new_flight();
    config_ = config;
    armed_ = true;
    pad_hold_ = COMMANDED_PAD_HOLD_S;
    stage_time_ = 0.0;
    return true;
}

void FlightSimulator::reset() {
    if (stage_ != Stage::Pad || armed_) start_new_flight();
}

void FlightSimulator::advance(double dt) {
    stage_time_ += dt;

    // On the ground the accelerometer reads +1 g: it measures the pad pushing
    // up on the rocket, not gravity itself.
    if (stage_ == Stage::Pad) {
        specific_force_ = G;
        if (armed_ && stage_time_ >= pad_hold_) enter(Stage::Boost);
        return;
    }
    if (stage_ == Stage::Landed) {
        specific_force_ = G;
        if (autolaunch_ && stage_time_ >= AUTOLAUNCH_LANDED_HOLD_S) {
            start_new_flight();
            armed_ = true;
            pad_hold_ = AUTOLAUNCH_PAD_HOLD_S;
        }
        return;
    }

    const bool boosting = stage_ == Stage::Boost;
    const double burned = boosting ? std::min(stage_time_ / config_.burn_time_s, 1.0) : 1.0;
    const double mass = config_.dry_mass_kg + config_.propellant_mass_kg * (1.0 - burned);
    const double thrust = boosting ? config_.thrust_n : 0.0;

    const double drag_area = stage_ == Stage::Descent
        ? config_.chute_drag_coefficient * disc_area(config_.chute_diameter_m)
        : config_.drag_coefficient * disc_area(config_.diameter_m);
    const double density = air_density(PAD_ELEVATION_M + altitude_);
    const double drag = -0.5 * density * drag_area * velocity_ * std::fabs(velocity_);

    // Specific force is every force except gravity, so in free fall it is ~0.
    specific_force_ = (thrust + drag) / mass;
    velocity_ += (specific_force_ - G) * dt;
    altitude_ += velocity_ * dt;
    east_ += WIND_EAST * dt;
    north_ += WIND_NORTH * dt;

    if (boosting && altitude_ < 0.0) {
        // Not enough thrust to leave the pad.
        altitude_ = 0.0;
        velocity_ = 0.0;
    }

    if (boosting && stage_time_ >= config_.burn_time_s) {
        enter(Stage::Coast);
    } else if (stage_ == Stage::Coast && velocity_ <= 0.0) {
        enter(Stage::Descent);  // parachute opens at apogee
    } else if (stage_ == Stage::Descent && altitude_ <= 0.0) {
        altitude_ = 0.0;
        velocity_ = 0.0;
        specific_force_ = G;
        enter(Stage::Landed);
    }
}

Reading FlightSimulator::step(double dt) {
    for (int i = 0; i < SUBSTEPS; ++i) advance(dt / SUBSTEPS);
    elapsed_ += dt;

    const bool boosting = stage_ == Stage::Boost;
    const bool ascending = boosting || stage_ == Stage::Coast;
    const double lat = PAD_LAT + (north_ + noise(1.5)) / METERS_PER_DEGREE;
    const double lon_scale = METERS_PER_DEGREE * std::cos(PAD_LAT * PI / 180.0);

    Reading r;
    r.flight_id = flight_id_;
    // Motor vibration makes the IMU much noisier during the burn.
    r.accel_x = static_cast<float>(noise(boosting ? 0.6 : 0.15));
    r.accel_y = static_cast<float>(noise(boosting ? 0.6 : 0.15));
    r.accel_z = static_cast<float>(specific_force_ + noise(boosting ? 0.8 : 0.08));
    r.gyro_x = static_cast<float>(noise(0.03));
    r.gyro_y = static_cast<float>(noise(0.03));
    r.gyro_z = static_cast<float>((ascending ? ROLL_RATE : 0.0) + noise(0.03));
    r.pressure_hpa = static_cast<float>(pressure_hpa(PAD_ELEVATION_M + altitude_) + noise(0.1));
    r.altitude_m = static_cast<float>(altitude_ + noise(0.4));
    r.gps_lat = lat;
    r.gps_lon = PAD_LON + (east_ + noise(1.5)) / lon_scale;
    r.temperature_c = static_cast<float>(25.0 - 0.0065 * altitude_ + noise(0.3));
    r.battery_v = static_cast<float>(std::max(3.2, 4.2 - elapsed_ * 0.0008 + noise(0.005)));
    return r;
}

}  // namespace telemetry
