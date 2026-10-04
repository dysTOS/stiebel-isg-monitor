import datetime as dt
import json
import mimetypes
import os
import sqlite3
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .registers import ON_DEMAND_READ_BLOCKS, REGISTERS
from .storage import SERIES_NAMES, Store


BACKUP_TABLES = {
    "measurements": ("timestamp_utc", "address", "name", "raw_value", "value", "unit", "error"),
    "connection_events": ("timestamp_utc", "event", "detail"),
    "compressor_runs": ("started_utc", "ended_utc", "duration_seconds", "heating", "dhw", "complete"),
    "compressor_phases": ("started_utc", "ended_utc", "duration_seconds", "run_started_utc", "heating", "dhw", "complete"),
    "counter_events": ("timestamp_utc", "name", "previous", "current", "event"),
}
MAX_BACKUP_BYTES = 512 * 1024 * 1024


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
        status_rows = db.execute("""
            SELECT timestamp_utc, name, value FROM measurements
            WHERE timestamp_utc >= ?
              AND name IN ('operating_status', 'heating_circuit_pump_1')
              AND value IS NOT NULL AND error IS NULL
            ORDER BY timestamp_utc, rowid
        """, (cutoff,)).fetchall()
        status_samples = {}
        for row in status_rows:
            sample = status_samples.setdefault(row["timestamp_utc"], {
                "timestamp_utc": row["timestamp_utc"],
                "operating_status": None,
                "heating_circuit_pump_1": None,
            })
            sample[row["name"]] = row["value"]
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
        run_rows = db.execute("""
            SELECT started_utc, ended_utc, duration_seconds, heating, dhw, complete
            FROM compressor_runs ORDER BY started_utc DESC LIMIT 50
        """).fetchall()
        runs = [dict(row) for row in run_rows]
        phases_by_run = {}
        if runs:
            run_placeholders = ",".join("?" for _ in runs)
            phase_rows = db.execute(f"""
                SELECT started_utc, ended_utc, duration_seconds, run_started_utc,
                       heating, dhw, complete
                FROM compressor_phases
                WHERE run_started_utc IN ({run_placeholders})
                ORDER BY started_utc, rowid
            """, tuple(run["started_utc"] for run in runs)).fetchall()
            for phase in phase_rows:
                phases_by_run.setdefault(phase["run_started_utc"], []).append(dict(phase))
        for run in runs:
            run["phases"] = phases_by_run.get(run["started_utc"], [])
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
            "status_samples": list(status_samples.values()),
            "daily": daily,
            "today": today,
            "runs": runs,
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


def _create_backup(db_path):
    fd, backup_path = tempfile.mkstemp(prefix="stiebel-backup-", suffix=".sqlite3")
    os.close(fd)
    try:
        source = _database(db_path)
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return Path(backup_path)
    except Exception:
        Path(backup_path).unlink(missing_ok=True)
        raise


def _replace_database(db_path, backup_path):
    """Replace application rows from a validated SQLite backup atomically."""
    db = _database(db_path)
    try:
        db.execute("ATTACH DATABASE ? AS backup", (str(backup_path),))
        integrity = db.execute("PRAGMA backup.integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError("Die Sicherungsdatei ist beschädigt")
        available = {
            row[0] for row in db.execute(
                "SELECT name FROM backup.sqlite_master WHERE type='table'"
            )
        }
        for table, columns in BACKUP_TABLES.items():
            if table not in available:
                raise ValueError(f"Die Sicherung enthält keine Tabelle {table}")
            actual = tuple(row[1] for row in db.execute(f"PRAGMA backup.table_info({table})"))
            if actual != columns:
                raise ValueError(f"Die Tabelle {table} hat ein inkompatibles Format")

        db.execute("BEGIN IMMEDIATE")
        for table, columns in BACKUP_TABLES.items():
            column_list = ", ".join(columns)
            db.execute(f"DELETE FROM main.{table}")
            db.execute(f"INSERT INTO main.{table} ({column_list}) SELECT {column_list} FROM backup.{table}")
        db.commit()
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        try:
            db.execute("DETACH DATABASE backup")
        except sqlite3.Error:
            pass
        db.close()


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
        if parsed.path == "/api/backup":
            backup_path = None
            headers_sent = False
            try:
                backup_path = _create_backup(self.server.db_path)
                size = backup_path.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.sqlite3")
                self.send_header("Content-Disposition", f'attachment; filename="stiebel-monitor-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}.sqlite3"')
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                headers_sent = True
                with backup_path.open("rb") as backup_file:
                    while chunk := backup_file.read(64 * 1024):
                        self.wfile.write(chunk)
            except (OSError, sqlite3.Error) as exc:
                if not headers_sent:
                    self._json({"error": f"Sicherung konnte nicht erstellt werden: {exc}"}, 500)
            finally:
                if backup_path is not None:
                    backup_path.unlink(missing_ok=True)
            return
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
        files = {"/": "index.html", "/registers": "registers.html", "/app.js": "app.js", "/charts.js": "charts.js", "/registers.js": "registers.js", "/pwa.js": "pwa.js", "/style.css": "style.css", "/manifest.webmanifest": "manifest.webmanifest", "/sw.js": "sw.js", "/icon.svg": "icon.svg", "/icon-192.png": "icon-192.png", "/icon-512.png": "icon-512.png"}
        filename = files.get(parsed.path)
        if filename is None:
            self.send_error(404)
            return
        path = self.server.static_dir / filename
        data = path.read_bytes()
        self.send_response(200)
        content_type = "application/manifest+json" if path.suffix == ".webmanifest" else mimetypes.guess_type(path.name)[0]
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if urlparse(self.path).path != "/api/backup/import":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json({"error": "Ungültige Dateigröße"}, 400)
            return
        if length <= 0 or length > MAX_BACKUP_BYTES:
            self._json({"error": "Die Sicherungsdatei ist leer oder größer als 512 MB"}, 413)
            return

        backup_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="stiebel-import-", suffix=".sqlite3", delete=False) as upload:
                backup_path = Path(upload.name)
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(64 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Die Übertragung der Sicherungsdatei war unvollständig")
                    upload.write(chunk)
                    remaining -= len(chunk)

            with self.server.monitor.database_lock:
                _replace_database(self.server.db_path, backup_path)
                store = Store(self.server.db_path)
                try:
                    self.server.monitor.previous_status = None
                    self.server.monitor.last_status_at = None
                    self.server.monitor.run_start = None
                    self.server.monitor.phase_start = None
                    self.server.monitor.previous_counters = {}
                    self.server.monitor.restore_open_run(store)
                finally:
                    store.close()
            self._json({"ok": True})
        except (ValueError, sqlite3.Error, OSError) as exc:
            self._json({"error": str(exc)}, 400)
        finally:
            if backup_path is not None:
                backup_path.unlink(missing_ok=True)

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
