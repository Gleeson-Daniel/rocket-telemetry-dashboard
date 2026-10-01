import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "telemetry.db"

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._create_table()

    def _create_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER,
                data TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS phase_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER,
                flight_id INTEGER,
                from_phase TEXT,
                to_phase TEXT,
                altitude_m REAL
            )
        """)
        self.conn.commit()

    def save(self, data: dict):
        self.conn.execute(
            "INSERT INTO readings (timestamp, data) VALUES (?, ?)",
            (data["timestamp"], json.dumps(data))
        )
        self.conn.commit()

    def get_recent(self, limit: int = 500) -> list:
        cursor = self.conn.execute(
            "SELECT data FROM readings ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = [json.loads(row[0]) for row in cursor.fetchall()]
        return list(reversed(rows))

    def save_transition(self, transition: dict):
        self.conn.execute(
            "INSERT INTO phase_transitions"
            " (timestamp, flight_id, from_phase, to_phase, altitude_m)"
            " VALUES (?, ?, ?, ?, ?)",
            (transition["timestamp"], transition["flight_id"],
             transition["from_phase"], transition["to_phase"],
             transition["altitude_m"])
        )
        self.conn.commit()

    def get_transitions(self, limit: int = 50) -> list:
        cursor = self.conn.execute(
            "SELECT timestamp, flight_id, from_phase, to_phase, altitude_m"
            " FROM phase_transitions ORDER BY id DESC LIMIT ?", (limit,)
        )
        keys = ("timestamp", "flight_id", "from_phase", "to_phase", "altitude_m")
        rows = [dict(zip(keys, row)) for row in cursor.fetchall()]
        return list(reversed(rows))
