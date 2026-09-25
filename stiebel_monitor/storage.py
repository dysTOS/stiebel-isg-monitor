import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (timestamp_utc TEXT NOT NULL, address INTEGER NOT NULL, name TEXT NOT NULL, raw_value INTEGER, value REAL, unit TEXT, error TEXT);
CREATE INDEX IF NOT EXISTS ix_measurements_time ON measurements(timestamp_utc);
CREATE TABLE IF NOT EXISTS connection_events (timestamp_utc TEXT NOT NULL, event TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS compressor_runs (started_utc TEXT NOT NULL, ended_utc TEXT, duration_seconds REAL, heating INTEGER, dhw INTEGER, complete INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS counter_events (timestamp_utc TEXT NOT NULL, name TEXT NOT NULL, previous REAL, current REAL, event TEXT NOT NULL);
"""

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.executescript(SCHEMA)
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_measurements_name_time ON measurements(name, timestamp_utc)")
        self.db.commit()
    def measurement(self, ts, reg, raw, value, error=None):
        self.db.execute("INSERT INTO measurements VALUES (?,?,?,?,?,?,?)", (ts, reg.address, reg.name, raw, value, reg.unit, error))
    def event(self, ts, event, detail=""): self.db.execute("INSERT INTO connection_events VALUES (?,?,?)", (ts, event, detail))
    def run(self, started, ended, duration, heating, dhw, complete=1): self.db.execute("INSERT INTO compressor_runs VALUES (?,?,?,?,?,?)", (started, ended, duration, heating, dhw, complete))
    def start_run(self, started, heating, dhw, complete=1):
        self.db.execute("INSERT INTO compressor_runs VALUES (?,NULL,NULL,?,?,?)", (started, int(heating), int(dhw), complete))
    def finish_run(self, started, ended, duration, complete=None):
        if complete is None:
            self.db.execute("UPDATE compressor_runs SET ended_utc=?, duration_seconds=? WHERE rowid=(SELECT max(rowid) FROM compressor_runs WHERE started_utc=? AND ended_utc IS NULL)", (ended, duration, started))
        else:
            self.db.execute("UPDATE compressor_runs SET ended_utc=?, duration_seconds=?, complete=? WHERE rowid=(SELECT max(rowid) FROM compressor_runs WHERE started_utc=? AND ended_utc IS NULL)", (ended, duration, complete, started))
    def open_run(self):
        return self.db.execute("SELECT started_utc, heating, dhw, complete FROM compressor_runs WHERE ended_utc IS NULL ORDER BY rowid DESC LIMIT 1").fetchone()
    def counter_event(self, ts, name, previous, current, event): self.db.execute("INSERT INTO counter_events VALUES (?,?,?,?,?)", (ts, name, previous, current, event))
    def commit(self): self.db.commit()
    def close(self): self.db.close()
