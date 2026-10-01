#include <algorithm>
#include <limits>

#include "check.hpp"
#include "flight_sim.hpp"

namespace {

constexpr double DT = 0.1;

struct FlightResult {
    double peak_altitude = 0.0;
    double peak_accel = 0.0;
    double final_altitude = 0.0;
    double seconds = 0.0;
};

// Steps the simulator for a fixed length of flight time.
FlightResult fly(telemetry::FlightSimulator& sim, double seconds) {
    FlightResult result;
    for (double t = 0.0; t < seconds; t += DT) {
        const telemetry::Reading r = sim.step(DT);
        result.peak_altitude = std::max<double>(result.peak_altitude, r.altitude_m);
        result.peak_accel = std::max<double>(result.peak_accel, r.accel_z);
        result.final_altitude = r.altitude_m;
    }
    result.seconds = seconds;
    return result;
}

void test_waits_on_the_pad_until_launched() {
    telemetry::FlightSimulator sim(1);
    const FlightResult result = fly(sim, 30.0);
    CHECK(result.peak_altitude < 3.0);
    CHECK(result.peak_accel < 11.0);
    CHECK(sim.flight_id() == 1);
}

void test_default_rocket_flies_and_lands() {
    telemetry::FlightSimulator sim(1);
    CHECK(sim.launch(telemetry::RocketConfig{}));
    const FlightResult result = fly(sim, 120.0);
    CHECK(result.peak_altitude > 500.0 && result.peak_altitude < 900.0);
    CHECK(result.peak_accel > 40.0);
    CHECK(result.final_altitude < 3.0);
}

void test_heavier_rocket_flies_lower() {
    telemetry::FlightSimulator light(1), heavy(1);
    telemetry::RocketConfig heavy_config;
    heavy_config.dry_mass_kg = 4.0;
    light.launch(telemetry::RocketConfig{});
    heavy.launch(heavy_config);
    CHECK(fly(heavy, 120.0).peak_altitude < 0.6 * fly(light, 120.0).peak_altitude);
}

void test_bigger_parachute_descends_slower() {
    telemetry::RocketConfig big_chute;
    big_chute.chute_diameter_m = 1.2;
    telemetry::FlightSimulator small(1), big(1);
    small.launch(telemetry::RocketConfig{});
    big.launch(big_chute);
    // 80 s is long enough for the default rocket to land but not this one.
    CHECK(fly(small, 80.0).final_altitude < 3.0);
    CHECK(fly(big, 80.0).final_altitude > 100.0);
}

void test_underpowered_rocket_stays_on_the_pad() {
    telemetry::RocketConfig weak;
    weak.thrust_n = 10.0;  // the rocket weighs about 22.6 N
    telemetry::FlightSimulator sim(1);
    CHECK(sim.launch(weak));
    CHECK(fly(sim, 30.0).peak_altitude < 3.0);
}

void test_invalid_rocket_is_refused() {
    telemetry::FlightSimulator sim(1);
    telemetry::RocketConfig zero_mass;
    zero_mass.dry_mass_kg = 0.0;
    telemetry::RocketConfig not_a_number;
    not_a_number.thrust_n = std::numeric_limits<double>::quiet_NaN();

    CHECK(!sim.launch(zero_mass));
    CHECK(!sim.launch(not_a_number));
    CHECK(fly(sim, 10.0).peak_altitude < 3.0);
}

void test_launching_again_starts_a_new_flight() {
    telemetry::FlightSimulator sim(1);
    sim.launch(telemetry::RocketConfig{});
    CHECK(sim.flight_id() == 1);
    fly(sim, 10.0);

    sim.launch(telemetry::RocketConfig{});
    CHECK(sim.flight_id() == 2);
    CHECK(fly(sim, 0.5).peak_altitude < 3.0);
}

void test_reset_returns_to_the_pad() {
    telemetry::FlightSimulator sim(1);
    sim.launch(telemetry::RocketConfig{});
    fly(sim, 10.0);

    sim.reset();
    CHECK(sim.flight_id() == 2);
    CHECK(fly(sim, 20.0).peak_altitude < 3.0);

    sim.reset();  // already on a fresh pad, so nothing changes
    CHECK(sim.flight_id() == 2);
}

void test_autolaunch_flies_without_a_command() {
    telemetry::FlightSimulator sim(1, true);
    CHECK(fly(sim, 60.0).peak_altitude > 500.0);
}

}  // namespace

int main() {
    test_waits_on_the_pad_until_launched();
    test_default_rocket_flies_and_lands();
    test_heavier_rocket_flies_lower();
    test_bigger_parachute_descends_slower();
    test_underpowered_rocket_stays_on_the_pad();
    test_invalid_rocket_is_refused();
    test_launching_again_starts_a_new_flight();
    test_reset_returns_to_the_pad();
    test_autolaunch_flies_without_a_command();
    return report("flight simulator");
}
