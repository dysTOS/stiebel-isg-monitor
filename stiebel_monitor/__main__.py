import argparse
import ipaddress
import os
import socket
import threading
from pathlib import Path

from .modbus import ModbusTCP
from .monitor import Monitor
from .registers import REGISTERS
from .web import make_server


def load_env_file(path=".env"):
    """Load a small KEY=VALUE env file without an external dependency."""
    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value[:1] == value[-1:] and value[:1] in ('"', "'"):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        raise SystemExit(f"Ungültiger Ganzzahlwert für {name}")


def env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        raise SystemExit(f"Ungültiger Zahlenwert für {name}")


def discover(args):
    network = ipaddress.ip_network(args.subnet, strict=False)
    found = []
    for ip in network.hosts():
        try:
            with socket.create_connection((str(ip), args.port), args.timeout):
                found.append(str(ip))
                print(ip)
        except OSError:
            pass
    return 0 if found else 1


def probe(args):
    print(f"TCP {args.host}:{args.port}: ", end="")
    try:
        with socket.create_connection((args.host, args.port), args.timeout):
            print("offen")
        client = ModbusTCP(args.host, args.port, args.unit, args.timeout)
        raw = client.read_input_registers(507)[0]
        print(f"Modbus FC04: verfügbar; Register 507 raw={raw} decoded={REGISTERS[507].decode(raw)} °C")
        return 0
    except Exception as exc:
        print(f"nicht erfolgreich ({exc})")
        return 1


def build_monitor(args):
    return Monitor(args.host, args.db, args.interval, args.port, args.unit, args.timeout)


def log(args):
    monitor = build_monitor(args)
    print(f"Logging {args.host}:{args.port} alle {args.interval}s nach {args.db} (Ctrl-C zum Beenden)")
    try:
        monitor.run()
    except KeyboardInterrupt:
        monitor.stop()
    return 0


def serve(args):
    monitor = build_monitor(args)
    thread = threading.Thread(target=monitor.run, name="isg-monitor", daemon=True)
    thread.start()
    server = make_server(args.listen, args.web_port, args.db, monitor)
    shown_host = "localhost" if args.listen in ("0.0.0.0", "127.0.0.1") else args.listen
    print(f"Monitoring {args.host}:{args.port} alle {args.interval}s")
    print(f"Dashboard: http://{shown_host}:{args.web_port}")
    print("Beenden mit Ctrl-C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWird beendet …")
    finally:
        server.shutdown()
        server.server_close()
        monitor.stop()
        thread.join(timeout=args.timeout + 2)
    return 0


def add_modbus_options(parser):
    parser.add_argument("--host", default=os.environ.get("STIEBEL_ISG_HOST"), help="IP-Adresse des ISG (STIEBEL_ISG_HOST)")
    parser.add_argument("--port", type=int, default=env_int("STIEBEL_ISG_PORT", 502), help="Modbus-TCP-Port")
    parser.add_argument("--unit", type=int, default=env_int("STIEBEL_ISG_UNIT", 1), help="Modbus Slave-ID")
    parser.add_argument("--timeout", type=float, default=env_float("STIEBEL_ISG_TIMEOUT", 5), help="Netzwerk-Timeout in Sekunden")


def add_monitor_options(parser):
    add_modbus_options(parser)
    parser.add_argument("--interval", type=int, default=env_int("STIEBEL_POLL_INTERVAL", 60), help="Messintervall in Sekunden")
    parser.add_argument("--db", default=os.environ.get("STIEBEL_DB_PATH", "data/measurements.sqlite3"), help="SQLite-Datei")


def main():
    load_env_file()
    parser = argparse.ArgumentParser(description="Lokaler Read-only-Monitor für Stiebel Eltron ISG")
    commands = parser.add_subparsers(dest="command", required=True)
    discover_parser = commands.add_parser("discover", help="Geräte mit offenem TCP/502 finden")
    discover_parser.add_argument("--subnet", required=True)
    discover_parser.add_argument("--port", type=int, default=502)
    discover_parser.add_argument("--timeout", type=float, default=.3)
    discover_parser.set_defaults(func=discover)
    probe_parser = commands.add_parser("probe", help="Verbindung und Register 507 testen")
    add_modbus_options(probe_parser)
    probe_parser.set_defaults(func=probe)
    log_parser = commands.add_parser("log", help="Nur Monitoring starten")
    add_monitor_options(log_parser)
    log_parser.set_defaults(func=log)
    serve_parser = commands.add_parser("serve", help="Monitoring und Web-Dashboard starten")
    add_monitor_options(serve_parser)
    serve_parser.add_argument("--listen", default=os.environ.get("STIEBEL_WEB_LISTEN", "127.0.0.1"), help="Web-Bind-Adresse; für LAN: 0.0.0.0")
    serve_parser.add_argument("--web-port", type=int, default=env_int("STIEBEL_WEB_PORT", 8080))
    serve_parser.set_defaults(func=serve)
    args = parser.parse_args()
    if args.command in ("probe", "log", "serve") and not args.host:
        parser.error("ISG-Adresse fehlt: STIEBEL_ISG_HOST in .env setzen oder --host verwenden")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
