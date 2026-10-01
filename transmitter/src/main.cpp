// Simulated flight computer: packs sensor readings into binary packets and
// sends them to the ground station over UDP, standing in for a radio link.
// It listens on the same socket for launch, pause, resume and reset commands
// coming back.

#ifdef _WIN32
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0600
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <fcntl.h>
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>

#include "command.hpp"
#include "flight_sim.hpp"
#include "packet.hpp"

namespace {

#ifdef _WIN32
using socket_t = SOCKET;
void close_socket(socket_t s) { closesocket(s); }
void make_non_blocking(socket_t s) {
    u_long enabled = 1;
    ioctlsocket(s, FIONBIO, &enabled);
}
#else
using socket_t = int;
constexpr socket_t INVALID_SOCKET = -1;
void close_socket(socket_t s) { close(s); }
void make_non_blocking(socket_t s) { fcntl(s, F_SETFL, fcntl(s, F_GETFL, 0) | O_NONBLOCK); }
#endif

struct Options {
    std::string host = "127.0.0.1";
    std::string port = "9000";
    double rate_hz = 10.0;
    double speedup = 1.0;
    std::uint32_t count = 0;  // 0 = run until killed
    std::uint32_t seed = std::random_device{}();
    bool autolaunch = false;
    // Fault injection, each a probability per packet, to imitate a lossy link.
    double corrupt = 0.0;
    double drop = 0.0;
    double reorder = 0.0;
    std::string dump_path;  // write packets to a file instead of sending them
};

void print_usage() {
    std::cout << "usage: transmitter [options]\n"
                 "  --host HOST     ground station address (default 127.0.0.1)\n"
                 "  --port PORT     ground station UDP port (default 9000)\n"
                 "  --rate HZ       packets per second of flight time (default 10)\n"
                 "  --speedup N     run the flight N times faster than real time\n"
                 "  --count N       stop after N packets (default: run forever)\n"
                 "  --seed N        seed for sensor noise and fault injection\n"
                 "  --autolaunch    fly the default rocket on a loop without waiting\n"
                 "                  for a launch command\n"
                 "  --corrupt P     probability of flipping a bit in a packet\n"
                 "  --drop P        probability of not sending a packet\n"
                 "  --reorder P     probability of sending a packet after the next one\n"
                 "  --dump FILE     write packets to FILE as fast as possible, no UDP\n";
}

Options parse_args(int argc, char** argv) {
    Options opts;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            print_usage();
            std::exit(0);
        }
        if (arg == "--autolaunch") {
            opts.autolaunch = true;
            continue;
        }
        if (i + 1 >= argc) throw std::invalid_argument("missing value for " + arg);
        const std::string value = argv[++i];
        if (arg == "--host") opts.host = value;
        else if (arg == "--port") opts.port = value;
        else if (arg == "--rate") opts.rate_hz = std::stod(value);
        else if (arg == "--speedup") opts.speedup = std::stod(value);
        else if (arg == "--count") opts.count = static_cast<std::uint32_t>(std::stoul(value));
        else if (arg == "--seed") opts.seed = static_cast<std::uint32_t>(std::stoul(value));
        else if (arg == "--corrupt") opts.corrupt = std::stod(value);
        else if (arg == "--drop") opts.drop = std::stod(value);
        else if (arg == "--reorder") opts.reorder = std::stod(value);
        else if (arg == "--dump") opts.dump_path = value;
        else throw std::invalid_argument("unknown option " + arg);
    }
    if (opts.rate_hz <= 0.0) throw std::invalid_argument("--rate must be positive");
    if (opts.speedup <= 0.0) throw std::invalid_argument("--speedup must be positive");
    return opts;
}

class UdpLink {
public:
    UdpLink(const std::string& host, const std::string& port) {
#ifdef _WIN32
        WSADATA wsa;
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) throw std::runtime_error("WSAStartup failed");
#endif
        addrinfo hints{};
        hints.ai_family = AF_INET;
        hints.ai_socktype = SOCK_DGRAM;

        // Under Docker Compose the ground station's name may not resolve
        // until its container is up, so retry for a while before giving up.
        addrinfo* result = nullptr;
        for (int attempt = 0; getaddrinfo(host.c_str(), port.c_str(), &hints, &result) != 0; ++attempt) {
            if (attempt == 30) throw std::runtime_error("cannot resolve " + host);
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }

        socket_ = socket(result->ai_family, result->ai_socktype, result->ai_protocol);
        if (socket_ == INVALID_SOCKET) {
            freeaddrinfo(result);
            throw std::runtime_error("cannot create UDP socket");
        }
        make_non_blocking(socket_);
        dest_ = result;
    }

    ~UdpLink() {
        if (dest_ != nullptr) freeaddrinfo(dest_);
        if (socket_ != INVALID_SOCKET) close_socket(socket_);
#ifdef _WIN32
        WSACleanup();
#endif
    }

    UdpLink(const UdpLink&) = delete;
    UdpLink& operator=(const UdpLink&) = delete;

    // UDP gives no delivery guarantee and neither does a radio, so a failed
    // send is ignored: the receiver notices the gap in sequence numbers.
    void send(const telemetry::Packet& packet) {
        sendto(socket_, reinterpret_cast<const char*>(packet.data()),
               static_cast<int>(packet.size()), 0, dest_->ai_addr,
               static_cast<int>(dest_->ai_addrlen));
    }

    // Returns the next valid command the ground station has sent back to
    // this socket, without waiting. Anything that fails to decode is skipped.
    std::optional<telemetry::Command> receive() {
        std::uint8_t buffer[256];
        for (;;) {
            const auto received = recvfrom(socket_, reinterpret_cast<char*>(buffer),
                                           sizeof buffer, 0, nullptr, nullptr);
            if (received <= 0) return std::nullopt;
            auto command = telemetry::decode_command(buffer, static_cast<std::size_t>(received));
            if (command) return command;
        }
    }

private:
    socket_t socket_ = INVALID_SOCKET;
    addrinfo* dest_ = nullptr;
};

std::uint64_t unix_time_ms() {
    using namespace std::chrono;
    return static_cast<std::uint64_t>(
        duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count());
}

void apply(const telemetry::Command& command, telemetry::FlightSimulator& sim, bool& paused) {
    switch (command.type) {
    case telemetry::CommandType::Pause:
        paused = true;
        std::cerr << "pause command: simulation frozen" << std::endl;
        break;
    case telemetry::CommandType::Resume:
        paused = false;
        std::cerr << "resume command" << std::endl;
        break;
    case telemetry::CommandType::Reset:
        paused = false;
        sim.reset();
        std::cerr << "reset command: back on the pad" << std::endl;
        break;
    case telemetry::CommandType::Launch:
        if (sim.launch(command.config)) {
            paused = false;
            std::cerr << "launch command: flight " << static_cast<int>(sim.flight_id()) << std::endl;
        } else {
            std::cerr << "launch command ignored: invalid rocket" << std::endl;
        }
        break;
    }
}

int run(const Options& opts) {
    telemetry::FlightSimulator sim(opts.seed, opts.autolaunch);
    std::mt19937 fault_rng(opts.seed ^ 0x9E3779B9u);
    std::uniform_real_distribution<double> chance(0.0, 1.0);
    std::uniform_int_distribution<std::size_t> any_byte(0, telemetry::PACKET_SIZE - 1);
    std::uniform_int_distribution<int> any_bit(0, 7);

    const bool dumping = !opts.dump_path.empty();
    std::ofstream dump;
    std::optional<UdpLink> link;
    if (dumping) {
        dump.open(opts.dump_path, std::ios::binary);
        if (!dump) throw std::runtime_error("cannot open " + opts.dump_path);
    } else {
        link.emplace(opts.host, opts.port);
        std::cerr << "transmitting to " << opts.host << ":" << opts.port << " at "
                  << opts.rate_hz << " Hz"
                  << (opts.autolaunch ? "" : ", waiting on the pad for a launch command")
                  << std::endl;
    }

    const auto emit = [&](const telemetry::Packet& packet) {
        if (dumping) {
            dump.write(reinterpret_cast<const char*>(packet.data()),
                       static_cast<std::streamsize>(packet.size()));
        } else {
            link->send(packet);
        }
    };

    const double dt = 1.0 / opts.rate_hz;
    const auto period = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
        std::chrono::duration<double>(dt / opts.speedup));
    const std::uint64_t start_ms = unix_time_ms();
    auto next_tick = std::chrono::steady_clock::now();
    std::optional<telemetry::Packet> held;
    bool paused = false;

    for (std::uint32_t seq = 0; opts.count == 0 || seq < opts.count;) {
        if (link) {
            while (auto command = link->receive()) apply(*command, sim, paused);
        }
        // While paused the flight is frozen and nothing is transmitted, so
        // sequence numbers and timestamps pick up exactly where they left off.
        if (paused) {
            next_tick += period;
            std::this_thread::sleep_until(next_tick);
            continue;
        }

        telemetry::Reading reading = sim.step(dt);
        reading.sequence = seq;
        // Timestamps follow flight time, so they stay evenly spaced even
        // when the flight is run faster than real time.
        reading.timestamp_ms = start_ms + static_cast<std::uint64_t>(seq * dt * 1000.0);

        telemetry::Packet packet = telemetry::encode_packet(reading);

        if (chance(fault_rng) < opts.corrupt) {
            packet[any_byte(fault_rng)] ^= static_cast<std::uint8_t>(1u << any_bit(fault_rng));
        }
        // A dropped packet still uses up its sequence number.
        if (chance(fault_rng) >= opts.drop) {
            if (!held && chance(fault_rng) < opts.reorder) {
                held = packet;
            } else {
                emit(packet);
                if (held) {
                    emit(*held);
                    held.reset();
                }
            }
        }

        ++seq;
        if (!dumping) {
            next_tick += period;
            std::this_thread::sleep_until(next_tick);
        }
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        return run(parse_args(argc, argv));
    } catch (const std::exception& e) {
        std::cerr << "transmitter: " << e.what() << std::endl;
        return 1;
    }
}
