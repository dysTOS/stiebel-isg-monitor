import datetime as dt
import json
import mimetypes
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .registers import ON_DEMAND_READ_BLOCKS, REGISTERS
from .storage import Store


SERIES_NAMES = (
    "outside_temperature", "room_temperature_hc1", "room_temperature_fek", "room_temperature_hc1_wpm_system", "actual_temperature_hc1",
    "flow_temperature", "heat_pump_flow_temperature",
    "return_temperature", "buffer_temperature", "buffer_set_temperature",
    "dhw_temperature", "dhw_set_temperature",
)


def _database(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    return db


def _timezone(name=None):
    name = name or os.environ.get("STIEBEL_TIMEZONE", "Europe/Vienna")
    try:
        return ZoneInfo(name), name
    except ZoneInfoNotFoundError:
        return dt.datetime.now().astimezone().tzinfo, "local"


def _run_stats(rows, timezone):
    days = {}
    for row in rows:
        day = dt.datetime.fromisoformat(row["started_utc"]).astimezone(timezone).date().isoformat()
        item = days.setdefault(day, {"day": day, "starts": 0, "runtime_minutes": 0.0, "durations": []})
        item["starts"] += 1
        if row["duration_seconds"] is not None:
            minutes = row["duration_seconds"] / 60.0
            item["runtime_minutes"] += minutes
            item["durations"].append(minutes)
    return [
        {
            "day": item["day"],
            "starts": item["starts"],
            "runtime_minutes": round(item["runtime_minutes"], 1),
            "average_minutes": round(sum(item["durations"]) / len(item["durations"]), 1) if item["durations"] else None,
        }
        for item in sorted(days.values(), key=lambda value: value["day"])
    ]


def dashboard_data(db_path, monitor, hours=24, now=None, timezone_name=None):
    hours = min(24 * 31, max(1, int(hours)))
    now_utc = now or dt.datetime.now(dt.timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=dt.timezone.utc)
    timezone, timezone_label = _timezone(timezone_name)
    cutoff_dt = now_utc - dt.timedelta(hours=hours)
    cutoff = cutoff_dt.isoformat()
    bucket_seconds = max(60, int(hours * 3600 / 1000))
    local_today = now_utc.astimezone(timezone).date()
    today_start = dt.datetime.combine(local_today, dt.time.min, timezone).astimezone(dt.timezone.utc)
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
        stats_start = min(cutoff_dt, today_start).isoformat()
        stats_rows = db.execute("""
            SELECT started_utc, duration_seconds FROM compressor_runs
            WHERE started_utc >= ? ORDER BY started_utc
        """, (stats_start,)).fetchall()
        daily = _run_stats(
            [row for row in stats_rows if dt.datetime.fromisoformat(row["started_utc"]) >= cutoff_dt],
            timezone,
        )
        today_rows = [row for row in stats_rows if dt.datetime.fromisoformat(row["started_utc"]) >= today_start]
        today_stats = _run_stats(today_rows, timezone)
        today = today_stats[0] if today_stats else {
            "day": local_today.isoformat(), "starts": 0, "runtime_minutes": 0.0, "average_minutes": None,
        }
        runs = db.execute("""
            SELECT started_utc, ended_utc, duration_seconds, heating, dhw, complete
            FROM compressor_runs ORDER BY started_utc DESC LIMIT 50
        """).fetchall()
        events = db.execute("""
            SELECT timestamp_utc, event, detail FROM connection_events
            ORDER BY timestamp_utc DESC LIMIT 10
        """).fetchall()
        energy_names = ("heat_energy_heating_day", "heat_energy_dhw_day", "electric_energy_heating_day", "electric_energy_dhw_day")
        energy_placeholders = ",".join("?" for _ in energy_names)
        local_now = now_utc.astimezone(timezone)
        local_days = max(1, (hours + 23) // 24)
        energy_start = (local_now.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=local_days)).astimezone(dt.timezone.utc).isoformat()
        energy_rows = db.execute(f"""
            SELECT timestamp_utc, name, value FROM measurements
            WHERE name IN ({energy_placeholders}) AND timestamp_utc >= ? AND value IS NOT NULL
            ORDER BY timestamp_utc, rowid
        """, (*energy_names, energy_start)).fetchall()
        # Daily counters reset at local midnight, so group snapshots by the
        # host's local date rather than the UTC date stored in SQLite.
        energy_by_day = {}
        for row in energy_rows:
            local_day = dt.datetime.fromisoformat(row["timestamp_utc"]).astimezone(timezone).date().isoformat()
            energy_by_day.setdefault(local_day, {})[row["name"]] = row["value"]
        energy_daily = [
            {"day": day, "name": name, "value": values[name]}
            for day, values in sorted(energy_by_day.items())
            for name in energy_names if name in values
        ]
        counter_events = db.execute("""
            SELECT timestamp_utc, name, previous, current, event FROM counter_events
            ORDER BY timestamp_utc DESC LIMIT 10
        """).fetchall()
        return {
            "generated_at": now_utc.isoformat(),
            "hours": hours,
            "bucket_seconds": bucket_seconds,
            "timezone": timezone_label,
            "stale_after_seconds": max(180, monitor.interval * 3),
            "monitor": monitor.snapshot(),
            "latest": [dict(row) for row in latest],
            "series": [dict(row) for row in series],
            "daily": daily,
            "today": today,
            "runs": [dict(row) for row in runs],
            "events": [dict(row) for row in events],
            "energy_daily": [dict(row) for row in energy_daily],
            "counter_events": [dict(row) for row in counter_events],
        }
    finally:
        db.close()


def read_registers(monitor):
    """Read a fresh snapshot of every known register on explicit request."""
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    values = {}
    errors = {}
    for start, count in ON_DEMAND_READ_BLOCKS:
        try:
            with monitor.modbus_lock:
                raw_values = monitor.client.read_input_registers(start, count)
            for offset, raw in enumerate(raw_values):
                address = start + offset
                reg = REGISTERS.get(address)
                if reg is not None:
                    values[address] = {"raw_value": raw, "value": reg.decode(raw), "error": None}
        except Exception as exc:
            for address in range(start, start + count):
                if address in REGISTERS:
                    errors[address] = str(exc)
    return {
        "started_at": started_at,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "registers": [
            {
                "address": address,
                "name": reg.name,
                "category": reg.category,
                "profile": reg.profile,
                "unit": reg.unit,
                **values.get(address, {"raw_value": None, "value": None, "error": errors.get(address, "Nicht gelesen")}),
            }
            for address, reg in sorted(REGISTERS.items())
        ],
    }


class RegisterReadBusy(Exception):
    pass


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, db_path, monitor):
        self.db_path = db_path
        self.monitor = monitor
        self.static_dir = Path(__file__).with_name("static")
        self.register_read_lock = threading.Lock()
        self.register_cache = None
        super().__init__(address, handler)

    def register_snapshot(self):
        now = time.monotonic()
        if self.register_cache and now - self.register_cache[0] < 10:
            return self.register_cache[1]
        if not self.register_read_lock.acquire(blocking=False):
            raise RegisterReadBusy("Eine Registerabfrage läuft bereits")
        try:
            now = time.monotonic()
            if self.register_cache and now - self.register_cache[0] < 10:
                return self.register_cache[1]
            snapshot = read_registers(self.monitor)
            self.register_cache = (time.monotonic(), snapshot)
            return snapshot
        finally:
            self.register_read_lock.release()


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
        if parsed.path == "/api/registers":
            try:
                self._json(self.server.register_snapshot())
            except RegisterReadBusy as exc:
                self._json({"error": str(exc)}, 409)
            except Exception as exc:
                self._json({"error": str(exc)}, 502)
            return
        files = {"/": "index.html", "/registers": "registers.html", "/app.js": "app.js", "/charts.js": "charts.js", "/registers.js": "registers.js", "/style.css": "style.css"}
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
