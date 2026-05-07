from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from simulator import SensorSimulator
from database import Database

app = FastAPI(title="Telemetry API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database()
simulator = SensorSimulator()

@app.get("/")
def root():
    return {"status": "Telemetry server running"}

@app.get("/api/history")
def history(limit: int = 300):
    return db.get_recent(limit)

@app.websocket("/ws/telemetry")
async def telemetry_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            reading = simulator.next()
            db.save(reading)
            await websocket.send_json(reading)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass