import binascii
import random
import struct

import pytest

from protocol import (
    PACKET_SIZE, BadChecksum, BadLength, BadSync, BadVersion, PacketError,
    SequenceTracker, crc16_ccitt, decode_packet, encode_packet,
)

READING = {
    "flight_id": 3,
    "seq": 1234,
    "timestamp": 1_700_000_000_123,
    "imu_accel_x": 0.125,
    "imu_accel_y": -0.25,
    "imu_accel_z": 9.81,
    "imu_gyro_x": 0.01,
    "imu_gyro_y": -0.02,
    "imu_gyro_z": 2.0,
    "pressure_hpa": 1007.25,
    "altitude_m": 412.5,
    "gps_lat": 29.6516123,
    "gps_lon": -82.3248456,
    "temperature_c": 22.5,
    "battery_v": 4.125,
}


def with_crc(body: bytes) -> bytes:
    return body + struct.pack("<H", crc16_ccitt(body))


def test_crc_matches_published_check_value():
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_crc_agrees_with_the_standard_library():
    rng = random.Random(0)
    for _ in range(50):
        data = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 100)))
        assert crc16_ccitt(data) == binascii.crc_hqx(data, 0xFFFF)


def test_packet_is_66_bytes():
    assert PACKET_SIZE == 66
    assert len(encode_packet(READING)) == 66


def test_header_bytes_are_little_endian():
    packet = encode_packet(READING)

    assert packet[0:2] == b"\x5a\xa5"
    assert packet[2] == 1
    assert packet[3] == 3
    assert packet[4:8] == (1234).to_bytes(4, "little")
    assert packet[8:16] == (1_700_000_000_123).to_bytes(8, "little")


def test_round_trip_preserves_every_field():
    decoded = decode_packet(encode_packet(READING))

    assert decoded.keys() == READING.keys()
    for key, value in READING.items():
        assert decoded[key] == pytest.approx(value, abs=1e-3), key


def test_gps_keeps_seven_decimal_places():
    decoded = decode_packet(encode_packet(READING))

    assert decoded["gps_lat"] == pytest.approx(READING["gps_lat"], abs=1e-7)
    assert decoded["gps_lon"] == pytest.approx(READING["gps_lon"], abs=1e-7)


def test_every_single_bit_flip_is_rejected():
    packet = encode_packet(READING)

    for bit in range(PACKET_SIZE * 8):
        corrupted = bytearray(packet)
        corrupted[bit // 8] ^= 1 << (bit % 8)
        with pytest.raises(PacketError):
            decode_packet(bytes(corrupted))


def test_corrupted_payload_fails_the_checksum():
    corrupted = bytearray(encode_packet(READING))
    corrupted[44] ^= 0xFF

    with pytest.raises(BadChecksum):
        decode_packet(bytes(corrupted))


@pytest.mark.parametrize("size", [0, 1, PACKET_SIZE - 1, PACKET_SIZE + 1, 200])
def test_wrong_length_is_rejected(size):
    data = (encode_packet(READING) * 4)[:size]

    with pytest.raises(BadLength):
        decode_packet(data)


def test_wrong_sync_word_is_rejected_even_with_a_valid_crc():
    body = bytearray(encode_packet(READING)[:-2])
    body[0:2] = b"\x00\x00"

    with pytest.raises(BadSync):
        decode_packet(with_crc(bytes(body)))


def test_unknown_version_is_rejected_even_with_a_valid_crc():
    body = bytearray(encode_packet(READING)[:-2])
    body[2] = 99

    with pytest.raises(BadVersion):
        decode_packet(with_crc(bytes(body)))


def test_sequence_accepts_packets_in_order():
    tracker = SequenceTracker()

    assert all(tracker.accept(seq) for seq in range(100))
    assert tracker.lost == 0
    assert tracker.out_of_order == 0


def test_sequence_counts_dropped_packets():
    tracker = SequenceTracker()

    for seq in [0, 1, 2, 5, 6, 10]:
        assert tracker.accept(seq)

    assert tracker.lost == 5  # 3, 4, 7, 8, 9


def test_sequence_rejects_late_packets():
    tracker = SequenceTracker()

    accepted = [seq for seq in [0, 1, 3, 2, 4] if tracker.accept(seq)]

    assert accepted == [0, 1, 3, 4]
    assert tracker.out_of_order == 1


def test_sequence_rejects_duplicates():
    tracker = SequenceTracker()

    assert tracker.accept(7)
    assert not tracker.accept(7)
    assert tracker.out_of_order == 1


def test_sequence_resyncs_when_the_transmitter_restarts():
    tracker = SequenceTracker()
    for seq in range(500):
        tracker.accept(seq)

    assert tracker.accept(0)
    assert tracker.accept(1)
    assert tracker.lost == 0
