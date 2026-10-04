import datetime as dt
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (timestamp_utc TEXT NOT NULL, address INTEGER NOT NULL, name TEXT NOT NULL, raw_value INTEGER, value REAL, unit TEXT, error TEXT);
CREATE INDEX IF NOT EXISTS ix_measurements_time ON measurements(timestamp_utc);
CREATE TABLE IF NOT EXISTS connection_events (timestamp_utc TEXT NOT NULL, event TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS compressor_runs (started_utc TEXT NOT NULL, ended_utc TEXT, duration_seconds REAL, heating INTEGER, dhw INTEGER, complete INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS compressor_phases (started_utc TEXT NOT NULL, ended_utc TEXT, duration_seconds REAL, run_started_utc TEXT NOT NULL, heating INTEGER, dhw INTEGER, complete INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS counter_events (timestamp_utc TEXT NOT NULL, name TEXT NOT NULL, previous REAL, current REAL, event TEXT NOT NULL);
"""

# Keep raw history needed by the dashboard and compressor tracker. The register
# diagnostic page reads the remaining registers on demand, so they do not need
# a per-poll history here.
SERIES_NAMES = (
    "outside_temperature", "room_temperature_hc1", "room_temperature_fek", "room_temperature_hc1_wpm_system", "actual_temperature_hc1",
    "flow_temperature", "heat_pump_flow_temperature", "return_temperature", "buffer_temperature", "buffer_set_temperature",
    "dhw_temperature", "dhw_set_temperature", "heating_pressure",
)
HISTORICAL_MEASUREMENT_NAMES = frozenset((
    *SERIES_NAMES,
    "heat_pump_flow_temperature_1", "set_temperature_hc1_alt",
    "operating_status", "heating_circuit_pump_1", "fault_status",
    "heat_energy_heating_day", "heat_energy_dhw_day", "electric_energy_heating_day", "electric_energy_dhw_day",
    "flow_rate", "heat_pump_flow_rate",
    "compressor_heating_hours", "compressor_heating_hours_hp1", "compressor_heating_hours_wpm_system_hp1",
    "compressor_dhw_hours", "compressor_dhw_hours_hp1", "compressor_dhw_hours_wpm_system_hp1",
))

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.executescript(SCHEMA)
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_measurements_name_time ON measurements(name, timestamp_utc)")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_compressor_phases_run ON compressor_phases(run_started_utc, started_utc)")
        self.db.commit()
        placeholders = ",".join("?" for _ in HISTORICAL_MEASUREMENT_NAMES)
        self._last_measurement_state = {
            row[0]: (row[1], row[2], row[3])
            for row in self.db.execute(f"""
                SELECT m.name, m.raw_value, m.value, m.error
                FROM measurements m
                JOIN (
                    SELECT name, max(rowid) AS rid FROM measurements
                    WHERE name IN ({placeholders}) GROUP BY name
                ) latest ON latest.rid=m.rowid
            """, tuple(HISTORICAL_MEASUREMENT_NAMES))
        }
    def measurement(self, ts, reg, raw, value, error=None):
        if reg.name not in HISTORICAL_MEASUREMENT_NAMES:
            return
        state = (raw, value, error)
        previous = self._last_measurement_state.get(reg.name)
        repeated_unavailable = value is None and error is None and raw == 32768 and previous == state
        repeated_error = error is not None and previous is not None and previous[2] == error
        if repeated_unavailable or repeated_error:
            return
        self.db.execute("INSERT INTO measurements VALUES (?,?,?,?,?,?,?)", (ts, reg.address, reg.name, raw, value, reg.unit, error))
        self._last_measurement_state[reg.name] = state
    def event(self, ts, event, detail=""): self.db.execute("INSERT INTO connection_events VALUES (?,?,?)", (ts, event, detail))
    def run(self, started, ended, duration, heating, dhw, complete=1): self.db.execute("INSERT INTO compressor_runs VALUES (?,?,?,?,?,?)", (started, ended, duration, heating, dhw, complete))
    def start_run(self, started, heating, dhw, complete=1):
        self.db.execute("INSERT INTO compressor_runs VALUES (?,NULL,NULL,?,?,?)", (started, int(heating), int(dhw), complete))
    def finish_run(self, started, ended, duration, complete=None):
        if complete is None:
            self.db.execute("UPDATE compressor_runs SET ended_utc=?, duration_seconds=? WHERE rowid=(SELECT max(rowid) FROM compressor_runs WHERE started_utc=? AND ended_utc IS NULL)", (ended, duration, started))
        else:
            self.db.execute("UPDATE compressor_runs SET ended_utc=?, duration_seconds=?, complete=? WHERE rowid=(SELECT max(rowid) FROM compressor_runs WHERE started_utc=? AND ended_utc IS NULL)", (ended, duration, complete, started))
    def mark_run_incomplete(self, started):
        self.db.execute("UPDATE compressor_runs SET complete=0 WHERE rowid=(SELECT max(rowid) FROM compressor_runs WHERE started_utc=? AND ended_utc IS NULL)", (started,))
    def open_run(self):
        return self.db.execute("SELECT started_utc, heating, dhw, complete FROM compressor_runs WHERE ended_utc IS NULL ORDER BY rowid DESC LIMIT 1").fetchone()
    def start_phase(self, started, run_started, heating, dhw, complete=1):
        self.db.execute("INSERT INTO compressor_phases VALUES (?,NULL,NULL,?,?,?,?)", (started, run_started, int(heating), int(dhw), complete))
    def finish_phase(self, started, ended, duration, complete=None):
        if complete is None:
            self.db.execute("UPDATE compressor_phases SET ended_utc=?, duration_seconds=? WHERE rowid=(SELECT max(rowid) FROM compressor_phases WHERE started_utc=? AND ended_utc IS NULL)", (ended, duration, started))
        else:
            self.db.execute("UPDATE compressor_phases SET ended_utc=?, duration_seconds=?, complete=? WHERE rowid=(SELECT max(rowid) FROM compressor_phases WHERE started_utc=? AND ended_utc IS NULL)", (ended, duration, complete, started))
    def mark_phase_incomplete(self, started):
        self.db.execute("UPDATE compressor_phases SET complete=0 WHERE rowid=(SELECT max(rowid) FROM compressor_phases WHERE started_utc=? AND ended_utc IS NULL)", (started,))
    def open_phase(self, run_started):
        return self.db.execute("""
            SELECT started_utc, heating, dhw, complete FROM compressor_phases
            WHERE run_started_utc=? AND ended_utc IS NULL ORDER BY rowid DESC LIMIT 1
        """, (run_started,)).fetchone()
    def repair_mode_splits(self):
        """Undo mode splits produced by the short-lived status-gap implementation."""
        splits = self.db.execute("""
            SELECT previous.rowid, previous.started_utc, previous.ended_utc,
                   previous.heating, previous.dhw, current.rowid,
                   current.started_utc, current.ended_utc, current.duration_seconds,
                   current.heating, current.dhw
            FROM compressor_runs previous
            JOIN compressor_runs current ON current.rowid = previous.rowid + 1
            JOIN connection_events event
              ON event.event='status_gap'
             AND event.timestamp_utc=current.started_utc
             AND event.detail=previous.ended_utc || ' -> ' || current.started_utc
            WHERE previous.ended_utc IS NOT NULL
              AND (previous.heating != current.heating OR previous.dhw != current.dhw)
              AND NOT EXISTS (
                  SELECT 1 FROM compressor_phases phase
                  WHERE phase.run_started_utc=previous.started_utc
                     OR phase.run_started_utc=current.started_utc
              )
            ORDER BY previous.rowid
        """).fetchall()
        for previous_id, run_started, phase_ended, heating, dhw, current_id, phase_started, run_ended, run_duration, current_heating, current_dhw in splits:
            phase_duration = max(0, (dt.datetime.fromisoformat(phase_ended) - dt.datetime.fromisoformat(run_started)).total_seconds())
            self.db.execute("INSERT INTO compressor_phases VALUES (?,?,?,?,?,?,0)", (
                run_started, phase_ended, phase_duration, run_started, heating, dhw,
            ))
            self.db.execute("INSERT INTO compressor_phases VALUES (?,?,?,?,?,?,0)", (
                phase_started, run_ended, run_duration, run_started, current_heating, current_dhw,
            ))
            duration = None
            if run_ended is not None:
                duration = max(0, (dt.datetime.fromisoformat(run_ended) - dt.datetime.fromisoformat(run_started)).total_seconds())
            self.db.execute("""
                UPDATE compressor_runs SET ended_utc=?, duration_seconds=?, complete=0
                WHERE rowid=?
            """, (run_ended, duration, previous_id))
            self.db.execute("DELETE FROM compressor_runs WHERE rowid=?", (current_id,))
        return len(splits)
    def status_samples_since(self, timestamp):
        return self.db.execute("""
            SELECT timestamp_utc, value FROM measurements
            WHERE name='operating_status' AND value IS NOT NULL AND timestamp_utc >= ?
            ORDER BY timestamp_utc, rowid
        """, (timestamp,)).fetchall()
    def counter_event(self, ts, name, previous, current, event): self.db.execute("INSERT INTO counter_events VALUES (?,?,?,?,?)", (ts, name, previous, current, event))
    def commit(self): self.db.commit()
    def close(self): self.db.close()
