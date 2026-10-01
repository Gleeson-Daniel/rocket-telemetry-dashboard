#pragma once

#include <iostream>

// A tiny stand-in for a test framework. Unlike assert(), CHECK still runs in
// release builds, and a failure doesn't stop the remaining checks.
inline int failures = 0;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << __FILE__ << ":" << __LINE__ << ": CHECK failed: "      \
                      << #condition << std::endl;                               \
            ++failures;                                                         \
        }                                                                       \
    } while (false)

inline int report(const char* suite) {
    if (failures != 0) {
        std::cerr << failures << " check(s) failed in " << suite << std::endl;
        return 1;
    }
    std::cout << "all " << suite << " tests passed" << std::endl;
    return 0;
}
