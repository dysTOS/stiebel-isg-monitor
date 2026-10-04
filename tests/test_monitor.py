import datetime as dt
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from stiebel_monitor.monitor import Monitor
from stiebel_monitor.registers import ON_DEMAND_READ_BLOCKS, REGISTERS
from stiebel_monitor.storage import Store
from stiebel_monitor.web import DashboardServer, RegisterReadBusy, dashboard_data


class FakeClient:
    def __init__(self):
        self.compressor = True
        self.status = 1 << 6
        self.calls = 0
        self.fail_starts = set()

    def read_input_registers(self, start, count):
        self.calls += 1
        if start in self.fail_starts:
            raise OSError(f"read failed at {start}")
        values = [32768] * count
        known = {
            507: 149, 518: 236, 522: 479, 523: 470, 584: 215,
            2501: self.status if self.compressor else 0,
            3644: 116, 3645: 118,
        }
        for address, value in known.items():
            if start <= address < start + count:
                values[address - start] = value
        return values


class MonitorTest(unittest.TestCase):
    def test_polling_and_compressor_run(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "measurements.sqlite3"
            monitor = Monitor("example.invalid", db_path, interval=60)
            monitor.client = FakeClient()
            store = Store(db_path)
            monitor.poll_once(store)
            monitor.client.compressor = False
            monitor.poll_once(store)
            store.close()

            data = dashboard_data(db_path, monitor, 24)
            latest = {item["name"]: item["value"] for item in data["latest"]}
            self.assertEqual(latest["outside_temperature"], 14.9)
            self.assertEqual(latest["buffer_temperature"], 23.6)
            self.assertEqual(latest["compressor_heating_hours_wpm_system_hp1"], 116)
            self.assertEqual(latest["compressor_dhw_hours_wpm_system_hp1"], 118)
            self.assertEqual(len(data["runs"]), 1)
            self.assertTrue(data["monitor"]["connected"])

    def test_optional_register_failure_replaces_stale_value(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "measurements.sqlite3"
            monitor = Monitor("example.invalid", db_path)
            monitor.client = FakeClient()
            store = Store(db_path)
            monitor.poll_once(store)
            monitor.client.fail_starts.add(584)
            monitor.poll_once(store)
            store.close()

            db = sqlite3.connect(db_path)
            row = db.execute("""
                SELECT value, error FROM measurements
                WHERE name='room_temperature_hc1_wpm_system'
                ORDER BY rowid DESC LIMIT 1
            """).fetchone()
            db.close()
            self.assertIsNone(row[0])
            self.assertIn("read failed", row[1])

    def test_mode_change_while_compressor_runs_starts_a_new_phase(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "measurements.sqlite3"
            monitor = Monitor("example.invalid", db_path)
            monitor.client = FakeClient()
            store = Store(db_path)
            monitor.client.status = (1 << 6) | (1 << 5)
            with patch("stiebel_monitor.monitor.utc_now", side_effect=[
                "2026-09-26T16:44:00+00:00", "2026-09-26T16:45:00+00:00",
            ]):
                monitor.poll_once(store)
                monitor.client.status = (1 << 6) | (1 << 4)
                monitor.poll_once(store)
            rows = store.db.execute("""
                SELECT started_utc, ended_utc, heating, dhw, complete
                FROM compressor_runs ORDER BY rowid
            """).fetchall()
            phases = store.db.execute("""
                SELECT started_utc, ended_utc, heating, dhw, complete
                FROM compressor_phases ORDER BY rowid
            """).fetchall()
            store.close()

            self.assertEqual(rows, [
                ("2026-09-26T16:44:00+00:00", None, 0, 1, 0),
            ])
            self.assertEqual(phases, [
                ("2026-09-26T16:44:00+00:00", "2026-09-26T16:45:00+00:00", 0, 1, 0),
                ("2026-09-26T16:45:00+00:00", None, 1, 0, 1),
            ])

    def test_status_gap_splits_phases_but_not_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "measurements.sqlite3"
            monitor = Monitor("example.invalid", db_path, interval=60)
            monitor.client = FakeClient()
            store = Store(db_path)
            monitor.client.status = (1 << 6) | (1 << 5)
            with patch("stiebel_monitor.monitor.utc_now", side_effect=[
                "2026-09-26T16:44:00+00:00", "2026-09-26T17:00:00+00:00",
            ]):
                monitor.poll_once(store)
                monitor.client.status = (1 << 6) | (1 << 4)
                monitor.poll_once(store)
            rows = store.db.execute("""
                SELECT started_utc, ended_utc, duration_seconds, heating, dhw, complete
                FROM compressor_runs ORDER BY rowid
            """).fetchall()
            phases = store.db.execute("""
                SELECT started_utc, ended_utc, duration_seconds, heating, dhw, complete
                FROM compressor_phases ORDER BY rowid
            """).fetchall()
            events = store.db.execute("SELECT event FROM connection_events WHERE event='status_gap'").fetchall()
            store.close()

            self.assertEqual(rows, [
                ("2026-09-26T16:44:00+00:00", None, None, 0, 1, 0),
            ])
            self.assertEqual(phases, [
                ("2026-09-26T16:44:00+00:00", "2026-09-26T16:44:00+00:00", 0.0, 0, 1, 0),
                ("2026-09-26T17:00:00+00:00", None, None, 1, 0, 0),
            ])
            self.assertEqual(events, [("status_gap",)])

    def test_same_mode_status_gap_does_not_invent_another_start(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "measurements.sqlite3"
            monitor = Monitor("example.invalid", db_path, interval=60)
            monitor.client = FakeClient()
            store = Store(db_path)
            heating = (1 << 6) | (1 << 4)
            with patch("stiebel_monitor.monitor.utc_now", side_effect=[
                "2026-09-26T16:43:00+00:00",
                "2026-09-26T16:44:00+00:00",
                "2026-09-26T17:00:00+00:00",
            ]):
                monitor.client.status = 0
                monitor.poll_once(store)
                monitor.client.status = heating
                monitor.poll_once(store)
                monitor.poll_once(store)
            rows = store.db.execute("""
                SELECT started_utc, ended_utc, heating, dhw, complete
                FROM compressor_runs ORDER BY rowid
            """).fetchall()
            phases = store.db.execute("""
                SELECT started_utc, ended_utc, heating, dhw, complete
                FROM compressor_phases ORDER BY rowid
            """).fetchall()
            store.close()

            self.assertEqual(rows, [
                ("2026-09-26T16:44:00+00:00", None, 1, 0, 0),
            ])
            self.assertEqual(phases, [
                ("2026-09-26T16:44:00+00:00", None, 1, 0, 0),
            ])

    def test_restart_reconciles_mode_change_in_open_run(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "measurements.sqlite3"
            store = Store(db_path)
            store.start_run("2026-09-26T16:44:00+00:00", False, True, 1)
            status_reg = REGISTERS[2501]
            store.measurement("2026-09-26T16:44:00+00:00", status_reg, 96, 96)
            store.measurement("2026-09-26T16:45:00+00:00", status_reg, 80, 80)
            store.commit()
            monitor = Monitor("example.invalid", db_path)
            monitor.restore_open_run(store)
            rows = store.db.execute("""
                SELECT started_utc, ended_utc, heating, dhw, complete
                FROM compressor_runs ORDER BY rowid
            """).fetchall()
            phases = store.db.execute("""
                SELECT started_utc, ended_utc, heating, dhw, complete
                FROM compressor_phases ORDER BY rowid
            """).fetchall()
            store.close()

            self.assertEqual(rows, [
                ("2026-09-26T16:44:00+00:00", None, 0, 1, 1),
            ])
            self.assertEqual(phases, [
                ("2026-09-26T16:44:00+00:00", "2026-09-26T16:45:00+00:00", 0, 1, 1),
                ("2026-09-26T16:45:00+00:00", None, 1, 0, 1),
            ])

    def test_restart_repairs_legacy_mode_split(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "measurements.sqlite3"
            store = Store(db_path)
            first = "2026-09-26T16:44:00+00:00"
            boundary = "2026-09-26T16:45:00+00:00"
            store.run(first, boundary, 60, False, True, 0)
            store.start_run(boundary, True, False, 0)
            store.event(boundary, "status_gap", f"{boundary} -> {boundary}")
            status_reg = REGISTERS[2501]
            store.measurement(boundary, status_reg, 80, 80)
            store.commit()
            monitor = Monitor("example.invalid", db_path)
            monitor.restore_open_run(store)
            rows = store.db.execute("""
                SELECT started_utc, ended_utc, heating, dhw, complete
                FROM compressor_runs ORDER BY rowid
            """).fetchall()
            phases = store.db.execute("""
                SELECT started_utc, ended_utc, run_started_utc, heating, dhw, complete
                FROM compressor_phases ORDER BY rowid
            """).fetchall()
            store.close()

            self.assertEqual(rows, [(first, None, 0, 1, 0)])
            self.assertEqual(phases, [
                (first, boundary, first, 0, 1, 0),
                (boundary, None, first, 1, 0, 0),
            ])

    def test_today_uses_local_calendar_day_not_selected_range(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "measurements.sqlite3"
            monitor = Monitor("example.invalid", db_path)
            store = Store(db_path)
            # 00:30 in Vienna, deliberately outside the selected six hours.
            store.run("2026-09-25T22:30:00+00:00", "2026-09-25T23:00:00+00:00", 1800, 1, 0)
            # Previous local calendar day, also outside the chart range.
            store.run("2026-09-25T21:30:00+00:00", "2026-09-25T22:00:00+00:00", 1800, 1, 0)
            store.commit()
            store.close()

            now = dt.datetime(2026, 9, 26, 10, 0, tzinfo=dt.timezone.utc)
            data = dashboard_data(db_path, monitor, 6, now=now, timezone_name="Europe/Vienna")
            self.assertEqual(data["today"]["day"], "2026-09-26")
            self.assertEqual(data["today"]["starts"], 1)
            self.assertEqual(data["today"]["average_minutes"], 30.0)
            self.assertEqual(data["daily"], [])

    def test_on_demand_blocks_cover_all_declared_registers(self):
        covered = {
            address
            for start, count in ON_DEMAND_READ_BLOCKS
            for address in range(start, start + count)
        }
        self.assertEqual(set(REGISTERS) - covered, set())

    def test_register_snapshot_is_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "measurements.sqlite3"
            monitor = Monitor("example.invalid", db_path)
            monitor.client = FakeClient()
            server = DashboardServer.__new__(DashboardServer)
            server.monitor = monitor
            server.register_read_lock = threading.Lock()
            server.register_cache = None
            first = server.register_snapshot()
            calls = monitor.client.calls
            second = server.register_snapshot()
            self.assertIs(first, second)
            self.assertEqual(monitor.client.calls, calls)

    def test_parallel_register_snapshot_is_rejected(self):
        monitor = Monitor("example.invalid", ":memory:")
        server = DashboardServer.__new__(DashboardServer)
        server.monitor = monitor
        server.register_read_lock = threading.Lock()
        server.register_cache = None
        server.register_read_lock.acquire()
        try:
            with self.assertRaises(RegisterReadBusy):
                server.register_snapshot()
        finally:
            server.register_read_lock.release()


if __name__ == "__main__":
    unittest.main()
