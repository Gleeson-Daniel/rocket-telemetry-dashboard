#pragma once

#include <cstdint>
#include <random>

#include "packet.hpp"

namespace telemetry {

// The rocket being simulated. The defaults are a mid-power rocket on an
// H-class motor that reaches roughly 700 m.
struct RocketConfig {
    double dry_mass_kg = 2.0;         // everything except propellant
    double propellant_mass_kg = 0.3;
    double thrust_n = 120.0;          // average thrust over the burn
    double burn_time_s = 2.5;
    double diameter_m = 0.066;        // body tube
    double drag_coefficient = 0.5;
    double chute_diameter_m = 0.6;
    double chute_drag_coefficient = 0.8;

    // False if any value is zero, negative or not a number.
    bool valid() const;
};

// Simulates a single-stage rocket flying straight up: it sits on the pad,
// burns its motor, coasts to apogee, descends under a parachute and lands.
//
// By default it waits on the pad until launch() is called. With autolaunch
// it flies the default rocket over and over without being told to.
class FlightSimulator {
public:
    explicit FlightSimulator(std::uint32_t seed, bool autolaunch = false);

    // Starts a new flight with the given rocket. Returns false, and does
    // nothing, if the config is not valid.
    bool launch(const RocketConfig& config);

    // Abandons the current flight and puts the rocket back on the pad.
    void reset();

    // Advances the flight by dt seconds and returns noisy sensor values.
    // The caller fills in the sequence number and timestamp.
    Reading step(double dt);

    std::uint8_t flight_id() const { return flight_id_; }

private:
    enum class Stage { Pad, Boost, Coast, Descent, Landed };

    void advance(double dt);
    void enter(Stage stage);
    void start_new_flight();
    double noise(double sigma);

    std::mt19937 rng_;
    RocketConfig config_;
    bool autolaunch_;
    bool armed_;               // on the pad and counting down to ignition
    double pad_hold_;          // seconds to wait on the pad once armed
    Stage stage_ = Stage::Pad;
    double stage_time_ = 0.0;
    double elapsed_ = 0.0;
    double altitude_ = 0.0;        // m above the pad
    double velocity_ = 0.0;        // m/s, positive up
    double specific_force_ = 0.0;  // m/s^2, what the Z accelerometer feels
    double east_ = 0.0;            // m of wind drift from the pad
    double north_ = 0.0;
    std::uint8_t flight_id_ = 1;
};

}  // namespace telemetry
