import tempfile
import unittest
from pathlib import Path

from stiebel_monitor.monitor import Monitor
from stiebel_monitor.storage import Store
from stiebel_monitor.web import dashboard_data


class FakeClient:
    def __init__(self):
        self.compressor = True

    def read_input_registers(self, start, count):
        values = [32768] * count
        known = {507: 149, 518: 236, 522: 479, 523: 470, 2501: 1 << 6 if self.compressor else 0}
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
            self.assertEqual(len(data["runs"]), 1)
            self.assertTrue(data["monitor"]["connected"])


if __name__ == "__main__":
    unittest.main()
