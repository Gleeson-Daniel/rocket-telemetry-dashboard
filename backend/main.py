from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
import os
import socket
import time
from commands import (COMMAND_LAUNCH, COMMAND_PAUSE, COMMAND_RESET, COMMAND_RESUME,
                      RocketSpec, encode_command, estimate, problems)
from database import Database
from pipeline import TelemetryPipeline
from protocol import encode_packet
from replay import SAMPLE_RATE_HZ, FlightLog, FlightLogError, parse_flight_log

UDP_HOST = os.getenv("TELEMETRY_UDP_HOST", "0.0.0.0")
UDP_PORT = int(os.getenv("TELEMETRY_UDP_PORT", "9000"))

TRANSMITTER_TIMEOUT_S = 3.0
PAUSE_SETTLE_S = 0.5  # packets already on their way when a pause is sent
REPLAY_FLIGHT_ID = 0  # the transmitter never uses flight id 0
MAX_LOG_BYTES = 5 * 1024 * 1024
MAX_REPLAY_SPEED = 50

logger = logging.getLogger("uvicorn.error")


class GroundStation:
    """Everything the server shares between the UDP link, replays and clients."""

    def __init__(self):
        self.db = Database()
        self.pipeline = TelemetryPipeline()
        self.clients: set[WebSocket] = set()
        self.transmitter_addr = None
        self.transmitter_seen = 0.0
        self.replay = None  # {"name", "progress"} while a log is being replayed
        self.replay_task = None
        self.paused = False
        self.paused_at = 0.0
        # Commands go out on their own socket. On Windows a send to a port
        # nobody is listening on makes the sending socket's next receive
        # fail, and that must not happen to the socket telemetry arrives on.
        self.uplink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def source(self) -> dict:
        return {"mode": "replay", **self.replay} if self.replay else {"mode": "live"}

    def transmitter_connected(self) -> bool:
        return time.monotonic() - self.transmitter_seen < TRANSMITTER_TIMEOUT_S

    def heard_from_transmitter(self, addr):
        now = time.monotonic()
        self.transmitter_addr = addr
        self.transmitter_seen = now
        # A paused transmitter is silent. If it is still talking well after a
        # pause was sent, the command was lost, so stop claiming to be paused.
        if self.paused and self.replay is None and now - self.paused_at > PAUSE_SETTLE_S:
            self.paused = False

    def set_paused(self, paused: bool):
        self.paused = paused
        self.paused_at = time.monotonic()

    def send_command(self, command: int, spec: RocketSpec = None):
        """Sends to wherever telemetry last came from; the transmitter
        listens on the same socket it sends with."""
        waiting_while_paused = self.paused and self.transmitter_addr is not None
        if not (self.transmitter_connected() or waiting_while_paused):
            raise HTTPException(503, "No transmitter is sending telemetry, so there is "
                                     "nothing to send the command to. Start the transmitter.")
        self.uplink.sendto(encode_command(command, spec), self.transmitter_addr)

    async def publish(self, reading: dict, transition):
        """Persist a reading, then fan it out to every connected dashboard."""
        self.db.save(reading)
        if transition is not None:
            self.db.save_transition(transition)
            logger.info("flight %d: %s -> %s at %.1f m", transition["flight_id"],
                        transition["from_phase"], transition["to_phase"],
                        transition["altitude_m"])

        message = {
            "reading": reading,
            "link": self.pipeline.stats(),
            "transition": transition,
            "summary": self.pipeline.summary(),
            "source": self.source(),
        }
        for websocket in list(self.clients):
            try:
                await websocket.send_json(message)
            except Exception:
                self.clients.discard(websocket)

    def start_replay(self, name: str, log: FlightLog, speed: float):
        self.paused = False
        self.replay = {"name": name, "progress": 0.0}
        self.replay_task = asyncio.create_task(self._run_replay(log, speed))

    async def stop_replay(self):
        task = self.replay_task
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        # A task cancelled before it first ran never reaches its own cleanup.
        self.replay = None
        self.replay_task = None
        self.paused = False

    async def _run_replay(self, log: FlightLog, speed: float):
        """Feeds a log through the same packet checks and phase detector as
        live telemetry. Live packets are ignored until it finishes."""
        self.pipeline = TelemetryPipeline()
        loop = asyncio.get_running_loop()
        due = loop.time()
        start_ms = round(time.time() * 1000)
        period_ms = 1000 // SAMPLE_RATE_HZ
        try:
            for i, sample in enumerate(log.readings):
                while self.paused:
                    await asyncio.sleep(0.05)
                    due = loop.time()
                packet = encode_packet({**sample, "flight_id": REPLAY_FLIGHT_ID, "seq": i,
                                        "timestamp": start_ms + i * period_ms})
                reading, transition = self.pipeline.process(packet)
                # Don't show a made-up value for a channel the log never had.
                for channel in log.missing:
                    reading[channel] = None
                self.replay["progress"] = round((i + 1) / len(log.readings), 3)
                await self.publish(reading, transition)
                due += 1 / (SAMPLE_RATE_HZ * speed)
                await asyncio.sleep(max(0.0, due - loop.time()))
        finally:
            self.replay = None
            self.replay_task = None
            self.pipeline = TelemetryPipeline()


station = GroundStation()


class TelemetryReceiver(asyncio.DatagramProtocol):
    """Hands each UDP datagram from the transmitter to the ingest task."""

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    def datagram_received(self, data: bytes, addr):
        station.heard_from_transmitter(addr)
        try:
            self.queue.put_nowait(data)
        except asyncio.QueueFull:
            pass  # ingest has fallen behind; it shows up as lost packets

    def error_received(self, exc):
        pass


async def ingest(queue: asyncio.Queue):
    """Single consumer: validate, detect phase, persist, then fan out."""
    while True:
        datagram = await queue.get()
        if station.replay is not None:
            continue
        result = station.pipeline.process(datagram)
        if result is not None:
            await station.publish(*result)


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
        lambda: TelemetryReceiver(queue), local_addr=(UDP_HOST, UDP_PORT)
    )
    task = asyncio.create_task(ingest(queue))
    logger.info("listening for telemetry on udp://%s:%d", UDP_HOST, UDP_PORT)
    yield
    await station.stop_replay()
    task.cancel()
    transport.close()


app = FastAPI(title="Telemetry API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "Telemetry server running"}

@app.get("/api/history")
def history(limit: int = 300):
    return station.db.get_recent(limit)

@app.get("/api/transitions")
def transitions(limit: int = 50):
    return station.db.get_transitions(limit)

@app.get("/api/stats")
def stats():
    return station.pipeline.stats()

@app.get("/api/status")
def status():
    return {
        "source": station.source(),
        "transmitter_connected": station.transmitter_connected(),
        "paused": station.paused,
    }

@app.post("/api/launch")
async def launch(spec: RocketSpec):
    issues = problems(spec)
    if issues:
        raise HTTPException(400, " ".join(issues))
    await station.stop_replay()
    station.send_command(COMMAND_LAUNCH, spec)
    station.paused = False
    return estimate(spec)

# Pause, resume and stop act on whatever is playing: a replayed log if there
# is one, otherwise the simulated flight on the transmitter.

@app.post("/api/pause")
async def pause():
    if station.replay is None:
        station.send_command(COMMAND_PAUSE)
    station.set_paused(True)
    return {"paused": True}

@app.post("/api/resume")
async def resume():
    if station.replay is None:
        station.send_command(COMMAND_RESUME)
    station.set_paused(False)
    return {"paused": False}

@app.post("/api/stop")
async def stop():
    if station.replay is not None:
        await station.stop_replay()
    else:
        station.send_command(COMMAND_RESET)
        station.paused = False
    return {"status": "stopped"}

@app.post("/api/replay")
async def replay(file: UploadFile, speed: float = Form(1.0)):
    if not 1 <= speed <= MAX_REPLAY_SPEED:
        raise HTTPException(400, f"Speed must be between 1 and {MAX_REPLAY_SPEED}.")
    raw = await file.read(MAX_LOG_BYTES + 1)
    if len(raw) > MAX_LOG_BYTES:
        raise HTTPException(400, "The file is larger than 5 MB.")
    try:
        log = parse_flight_log(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise HTTPException(400, "The file is not text. Upload a CSV file.")
    except FlightLogError as error:
        raise HTTPException(400, str(error))

    await station.stop_replay()
    station.start_replay(file.filename or "flight log", log, speed)
    return log.info

@app.websocket("/ws/telemetry")
async def telemetry_stream(websocket: WebSocket):
    await websocket.accept()
    station.clients.add(websocket)
    try:
        # Clients only listen; reading is how we find out they have gone.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        station.clients.discard(websocket)
