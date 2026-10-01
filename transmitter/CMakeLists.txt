cmake_minimum_required(VERSION 3.16)
project(transmitter LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

if(NOT MSVC)
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

add_library(telemetry STATIC src/packet.cpp src/command.cpp src/flight_sim.cpp)
target_include_directories(telemetry PUBLIC include)

add_executable(transmitter src/main.cpp)
target_link_libraries(transmitter PRIVATE telemetry)
if(WIN32)
  target_link_libraries(transmitter PRIVATE ws2_32)
endif()
if(MINGW)
  # Link the runtime statically so the .exe runs without MinGW on the PATH.
  target_link_options(transmitter PRIVATE -static)
endif()

enable_testing()
foreach(test_name packet flight_sim)
  add_executable(test_${test_name} tests/test_${test_name}.cpp)
  target_link_libraries(test_${test_name} PRIVATE telemetry)
  if(MINGW)
    target_link_options(test_${test_name} PRIVATE -static)
  endif()
  add_test(NAME ${test_name} COMMAND test_${test_name})
endforeach()
