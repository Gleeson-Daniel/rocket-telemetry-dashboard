"""Tests of the HTTP and WebSocket API, with no transmitter running."""
import importlib
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SAMPLE_LOG = Path(__file__).resolve().parents[2] / "samples" / "sample_flight.csv"


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Use a throwaway database and let the OS pick a free UDP port, so the
    # tests don't touch real data or collide with a server that is running.
    monkeypatch.setenv("TELEMETRY_UDP_PORT", "0")
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    sys.modules.pop("main", None)
    main = importlib.import_module("main")
    with TestClient(main.app) as test_client:
        yield test_client
    main.station.db.conn.close()
    sys.modules.pop("main", None)


def upload(client, text, speed="50", name="flight.csv"):
    return client.post("/api/replay", files={"file": (name, text, "text/csv")},
                       data={"speed": speed})


def test_status_with_nothing_connected(client):
    assert client.get("/api/status").json() == {
        "source": {"mode": "live"}, "transmitter_connected": False, "paused": False}


def test_launch_without_a_transmitter_says_so(client):
    response = client.post("/api/launch", json={})

    assert response.status_code == 503
    assert "Start the transmitter" in response.json()["detail"]


def test_launch_refuses_a_rocket_that_cannot_lift_off(client):
    response = client.post("/api/launch", json={"thrust_n": 5})

    assert response.status_code == 400
    assert "never leave the pad" in response.json()["detail"]


def test_launch_refuses_values_out_of_range(client):
    assert client.post("/api/launch", json={"dry_mass_kg": -1}).status_code == 422


def test_replay_refuses_a_file_that_is_not_a_flight_log(client):
    response = upload(client, "name,score\nann,3\n")

    assert response.status_code == 400
    assert "altitude column" in response.json()["detail"]


def test_replay_refuses_a_binary_file(client):
    response = client.post("/api/replay", data={"speed": "1"},
                           files={"file": ("photo.png", b"\x89PNG\xff\xfe\x00", "image/png")})

    assert response.status_code == 400
    assert "not text" in response.json()["detail"]


@pytest.mark.parametrize("speed", ["0", "0.5", "51"])
def test_replay_refuses_a_speed_out_of_range(client, speed):
    assert upload(client, SAMPLE_LOG.read_text(), speed=speed).status_code == 400


def test_replayed_log_streams_to_the_dashboard(client):
    with client.websocket_connect("/ws/telemetry") as websocket:
        response = upload(client, SAMPLE_LOG.read_text(), name="sample_flight.csv")
        assert response.status_code == 200
        samples = response.json()["samples"]

        messages = [websocket.receive_json() for _ in range(samples)]

    first, last = messages[0], messages[-1]
    assert first["source"] == {"mode": "replay", "name": "sample_flight.csv",
                               "progress": pytest.approx(1 / samples, abs=1e-3)}
    assert last["source"]["progress"] == 1.0
    assert first["reading"]["flight_id"] == 0
    assert [m["reading"]["seq"] for m in messages] == list(range(samples))

    # Channels the log doesn't have are sent as null, not as made-up numbers.
    assert first["reading"]["battery_v"] is None
    assert first["reading"]["gps_lat"] is None
    assert first["reading"]["pressure_hpa"] is not None

    assert [m["transition"]["to_phase"] for m in messages if m["transition"]] == [
        "POWERED_ASCENT", "COAST", "APOGEE", "DESCENT", "LANDED"]
    assert 500 < last["summary"]["peak_altitude_m"] < 800
    assert last["link"]["accepted"] == samples

    assert client.get("/api/status").json()["source"] == {"mode": "live"}
    saved = client.get("/api/transitions").json()
    assert [t["to_phase"] for t in saved][-1] == "LANDED"


def test_replay_can_be_stopped(client):
    with client.websocket_connect("/ws/telemetry") as websocket:
        assert upload(client, SAMPLE_LOG.read_text(), speed="1").status_code == 200
        assert websocket.receive_json()["source"]["mode"] == "replay"
        assert client.get("/api/status").json()["source"]["mode"] == "replay"

        assert client.post("/api/stop").status_code == 200

    assert client.get("/api/status").json()["source"] == {"mode": "live"}


def test_replay_can_be_paused_and_resumed(client):
    with client.websocket_connect("/ws/telemetry") as websocket:
        assert upload(client, SAMPLE_LOG.read_text(), speed="50").status_code == 200
        websocket.receive_json()

        assert client.post("/api/pause").json() == {"paused": True}
        assert client.get("/api/status").json()["paused"] is True
        # The replay holds its place: progress is the same a moment later.
        held = client.get("/api/status").json()["source"]["progress"]
        time.sleep(0.5)
        assert client.get("/api/status").json()["source"]["progress"] == held
        assert held < 1.0

        assert client.post("/api/resume").json() == {"paused": False}
        seqs = []
        while not seqs or seqs[-1] < 200:
            seqs.append(websocket.receive_json()["reading"]["seq"])

    # Nothing was skipped or repeated across the pause.
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))


def test_stopping_a_paused_replay_clears_the_pause(client):
    with client.websocket_connect("/ws/telemetry") as websocket:
        upload(client, SAMPLE_LOG.read_text(), speed="1")
        websocket.receive_json()
        client.post("/api/pause")

        client.post("/api/stop")

    assert client.get("/api/status").json() == {
        "source": {"mode": "live"}, "transmitter_connected": False, "paused": False}


@pytest.mark.parametrize("action", ["pause", "resume", "stop"])
def test_controls_without_a_transmitter_or_replay_say_so(client, action):
    response = client.post(f"/api/{action}")

    assert response.status_code == 503
    assert "Start the transmitter" in response.json()["detail"]
