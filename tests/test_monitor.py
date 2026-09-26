import datetime as dt
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from stiebel_monitor.monitor import Monitor
from stiebel_monitor.registers import ON_DEMAND_READ_BLOCKS, REGISTERS
from stiebel_monitor.storage import Store
from stiebel_monitor.web import DashboardServer, RegisterReadBusy, dashboard_data


class FakeClient:
    def __init__(self):
        self.compressor = True
        self.calls = 0
        self.fail_starts = set()

    def read_input_registers(self, start, count):
        self.calls += 1
        if start in self.fail_starts:
            raise OSError(f"read failed at {start}")
        values = [32768] * count
        known = {
            507: 149, 518: 236, 522: 479, 523: 470, 584: 215,
            2501: 1 << 6 if self.compressor else 0,
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
