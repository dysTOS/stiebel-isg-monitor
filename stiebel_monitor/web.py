import datetime as dt
import json
import mimetypes
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .storage import Store


SERIES_NAMES = (
    "outside_temperature", "room_temperature_hc1", "actual_temperature_hc1",
    "flow_temperature", "heat_pump_flow_temperature",
    "return_temperature", "buffer_temperature", "buffer_set_temperature",
    "dhw_temperature", "dhw_set_temperature",
)


def _database(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    return db


def dashboard_data(db_path, monitor, hours=24):
    hours = min(24 * 31, max(1, int(hours)))
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat()
    bucket_seconds = max(60, int(hours * 3600 / 1000))
    db = _database(db_path)
    try:
        latest = db.execute("""
            SELECT m.name, m.value, m.unit, m.raw_value, m.timestamp_utc, m.error
            FROM measurements m
            JOIN (SELECT name, max(rowid) AS rid FROM measurements GROUP BY name) x
              ON m.rowid = x.rid
            ORDER BY m.name
        """).fetchall()
        placeholders = ",".join("?" for _ in SERIES_NAMES)
        series = db.execute(f"""
            SELECT min(timestamp_utc) AS timestamp_utc, name, avg(value) AS value FROM measurements
            WHERE timestamp_utc >= ? AND value IS NOT NULL AND name IN ({placeholders})
            GROUP BY name, CAST(strftime('%s', timestamp_utc) AS INTEGER) / ?
            ORDER BY timestamp_utc
        """, (cutoff, *SERIES_NAMES, bucket_seconds)).fetchall()
        daily = db.execute("""
            SELECT substr(started_utc,1,10) AS day, count(*) AS starts,
                   round(sum(coalesce(duration_seconds,0))/60.0,1) AS runtime_minutes,
                   round(avg(duration_seconds)/60.0,1) AS average_minutes
            FROM compressor_runs WHERE started_utc >= ? GROUP BY day ORDER BY day
        """, (cutoff,)).fetchall()
        runs = db.execute("""
            SELECT started_utc, ended_utc, duration_seconds, heating, dhw, complete
            FROM compressor_runs ORDER BY started_utc DESC LIMIT 50
        """).fetchall()
        events = db.execute("""
            SELECT timestamp_utc, event, detail FROM connection_events
            ORDER BY timestamp_utc DESC LIMIT 10
        """).fetchall()
        return {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "hours": hours,
            "monitor": monitor.snapshot(),
            "latest": [dict(row) for row in latest],
            "series": [dict(row) for row in series],
            "daily": [dict(row) for row in daily],
            "runs": [dict(row) for row in runs],
            "events": [dict(row) for row in events],
        }
    finally:
        db.close()


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, db_path, monitor):
        self.db_path = db_path
        self.monitor = monitor
        self.static_dir = Path(__file__).with_name("static")
        super().__init__(address, handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "StiebelMonitor/0.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            try:
                hours = parse_qs(parsed.query).get("hours", ["24"])[0]
                self._json(dashboard_data(self.server.db_path, self.server.monitor, hours))
            except (ValueError, sqlite3.Error) as exc:
                self._json({"error": str(exc)}, 400)
            return
        files = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
        filename = files.get(parsed.path)
        if filename is None:
            self.send_error(404)
            return
        path = self.server.static_dir / filename
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, value, status=200):
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        if self.path != "/api/dashboard":
            super().log_message(format, *args)


def make_server(listen, port, db_path, monitor):
    Store(db_path).close()
    return DashboardServer((listen, port), Handler, db_path, monitor)
