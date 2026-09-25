import datetime as dt
import threading
import time

from .modbus import ModbusTCP
from .registers import READ_BLOCKS, REGISTERS, STATUS_BITS
from .storage import Store


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Monitor:
    """Background read-only poller. It never issues a Modbus write function."""

    def __init__(self, host, db_path, interval=60, port=502, unit=1, timeout=5):
        self.client = ModbusTCP(host, port, unit, timeout)
        self.db_path = db_path
        self.interval = max(1, interval)
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        self.state = {"connected": False, "polling": False, "last_poll": None, "last_success": None, "error": None}
        self.previous_status = None
        self.run_start = None
        self.run_complete = True
        self.restored_open = False
        self.previous_counters = {}

    def snapshot(self):
        with self.state_lock:
            return dict(self.state)

    def _set_state(self, **values):
        with self.state_lock:
            self.state.update(values)

    def poll_once(self, store):
        timestamp = utc_now()
        values = {}
        errors = []
        self._set_state(polling=True, last_poll=timestamp)
        for start, count in READ_BLOCKS:
            try:
                raw_values = self.client.read_input_registers(start, count)
                for offset, raw in enumerate(raw_values):
                    address = start + offset
                    reg = REGISTERS.get(address)
                    if reg is None:
                        continue
                    value = reg.decode(raw)
                    store.measurement(timestamp, reg, raw, value)
                    values[address] = value
                    if reg.category == "counter" and value is not None:
                        previous = self.previous_counters.get(reg.name)
                        if previous is not None and value < previous:
                            store.counter_event(timestamp, reg.name, previous, value, "reset_or_wrap")
                        self.previous_counters[reg.name] = value
            except Exception as exc:
                errors.append(f"{start}-{start + count - 1}: {exc}")
                for address in range(start, start + count):
                    reg = REGISTERS.get(address)
                    if reg:
                        store.measurement(timestamp, reg, None, None, str(exc))

        status = values.get(2501)
        if status is not None:
            status = int(status)
            compressor = bool(status & (1 << STATUS_BITS["compressor"]))
            heating = bool(status & (1 << STATUS_BITS["heating"]))
            dhw = bool(status & (1 << STATUS_BITS["dhw"]))
            if self.restored_open:
                if compressor:
                    self.previous_status = (True, heating, dhw)
                else:
                    store.finish_run(self.run_start, timestamp, None, 0)
                    self.run_start = None
                    self.previous_status = (False, heating, dhw)
                self.restored_open = False
            elif compressor and not (self.previous_status and self.previous_status[0]):
                self.run_start = timestamp
                self.run_complete = self.previous_status is not None
                store.start_run(timestamp, heating, dhw, int(self.run_complete))
                self.previous_status = (compressor, heating, dhw)
            elif not compressor and self.previous_status and self.previous_status[0] and self.run_start:
                start_time = dt.datetime.fromisoformat(self.run_start)
                end_time = dt.datetime.fromisoformat(timestamp)
                store.finish_run(self.run_start, timestamp, (end_time - start_time).total_seconds())
                self.run_start = None
                self.previous_status = (compressor, heating, dhw)
            else:
                self.previous_status = (compressor, heating, dhw)

        if errors:
            detail = "; ".join(errors)
            store.event(timestamp, "poll_partial_error", detail)
            self._set_state(connected=bool(values), polling=False, last_success=timestamp if values else self.state.get("last_success"), error=detail)
        else:
            self._set_state(connected=True, polling=False, last_success=timestamp, error=None)
        store.commit()
        return values

    def run(self):
        store = Store(self.db_path)
        open_run = store.open_run()
        if open_run:
            self.run_start = open_run[0]
            self.run_complete = False
            self.restored_open = True
        try:
            while not self.stop_event.is_set():
                started = time.monotonic()
                try:
                    self.poll_once(store)
                except Exception as exc:
                    timestamp = utc_now()
                    store.event(timestamp, "poll_error", repr(exc))
                    store.commit()
                    self._set_state(connected=False, polling=False, error=str(exc))
                wait = max(0, self.interval - (time.monotonic() - started))
                self.stop_event.wait(wait)
        finally:
            store.close()

    def stop(self):
        self.stop_event.set()
