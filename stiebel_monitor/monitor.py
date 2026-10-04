import datetime as dt
import threading
import time

from .modbus import ModbusTCP
from .registers import OPTIONAL_READ_BLOCKS, READ_BLOCKS, REGISTERS, STATUS_BITS
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
        self.database_lock = threading.RLock()
        self.modbus_lock = threading.Lock()
        self.state = {"connected": False, "polling": False, "last_poll": None, "last_success": None, "error": None}
        self.previous_status = None
        self.last_status_at = None
        self.run_start = None
        self.phase_start = None
        self.previous_counters = {}

    def snapshot(self):
        with self.state_lock:
            return dict(self.state)

    def _set_state(self, **values):
        with self.state_lock:
            self.state.update(values)

    @staticmethod
    def _status(value):
        value = int(value)
        return (
            bool(value & (1 << STATUS_BITS["compressor"])),
            bool(value & (1 << STATUS_BITS["heating"])),
            bool(value & (1 << STATUS_BITS["dhw"])),
        )

    @staticmethod
    def _seconds(start, end):
        return max(0, (dt.datetime.fromisoformat(end) - dt.datetime.fromisoformat(start)).total_seconds())

    @property
    def status_gap_seconds(self):
        return max(180, self.interval * 3)

    def _finish_run(self, store, ended, complete=None):
        if not self.run_start:
            return
        store.finish_run(self.run_start, ended, self._seconds(self.run_start, ended), complete)
        self.run_start = None

    def _finish_phase(self, store, ended, complete=None):
        if not self.phase_start:
            return
        store.finish_phase(self.phase_start, ended, self._seconds(self.phase_start, ended), complete)
        self.phase_start = None

    def _start_run(self, store, timestamp, status, complete):
        self.run_start = timestamp
        self.phase_start = timestamp
        store.start_run(timestamp, status[1], status[2], complete)
        store.start_phase(timestamp, timestamp, status[1], status[2], complete)

    def _start_phase(self, store, timestamp, status, complete):
        self.phase_start = timestamp
        store.start_phase(timestamp, self.run_start, status[1], status[2], complete)

    def _process_status(self, store, timestamp, value, record_gap=True):
        current = self._status(value)
        previous = self.previous_status
        gap = False
        if self.last_status_at is not None:
            gap = self._seconds(self.last_status_at, timestamp) > self.status_gap_seconds

        if gap:
            if previous and previous[0] and not current[0]:
                self._finish_phase(store, self.last_status_at, 0)
                self._finish_run(store, self.last_status_at, 0)
            elif previous and previous[0] and current[0] and current[1:] != previous[1:]:
                store.mark_run_incomplete(self.run_start)
                self._finish_phase(store, self.last_status_at, 0)
                self._start_phase(store, timestamp, current, 0)
            elif previous and previous[0] and current[0] and self.run_start:
                store.mark_run_incomplete(self.run_start)
                if self.phase_start:
                    store.mark_phase_incomplete(self.phase_start)
            elif current[0]:
                self._start_run(store, timestamp, current, 0)
            if record_gap:
                store.event(timestamp, "status_gap", f"{self.last_status_at} -> {timestamp}")
        elif current[0] and previous and previous[0] and current[1:] != previous[1:]:
            self._finish_phase(store, timestamp)
            self._start_phase(store, timestamp, current, 1)
        elif current[0] and not (previous and previous[0]):
            self._start_run(store, timestamp, current, int(previous is not None))
        elif not current[0] and previous and previous[0]:
            self._finish_phase(store, timestamp)
            self._finish_run(store, timestamp)

        self.previous_status = current
        self.last_status_at = timestamp

    def restore_open_run(self, store):
        """Restore and reconcile an open run from persisted status samples."""
        store.repair_mode_splits()
        open_run = store.open_run()
        if not open_run:
            store.commit()
            return
        self.run_start = open_run[0]
        open_phase = store.open_phase(self.run_start)
        if open_phase is None:
            self.phase_start = self.run_start
            store.start_phase(self.phase_start, self.run_start, open_run[1], open_run[2], open_run[3])
            phase = (self.phase_start, open_run[1], open_run[2])
        else:
            self.phase_start = open_phase[0]
            phase = open_phase
        self.previous_status = (True, bool(phase[1]), bool(phase[2]))
        self.last_status_at = self.phase_start
        for timestamp, value in store.status_samples_since(self.phase_start):
            self._process_status(store, timestamp, value, record_gap=False)
        store.commit()

    def poll_once(self, store):
        timestamp = utc_now()
        values = {}
        errors = []
        self._set_state(polling=True, last_poll=timestamp)
        for start, count in READ_BLOCKS:
            try:
                with self.modbus_lock:
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

        for start, count in OPTIONAL_READ_BLOCKS:
            try:
                with self.modbus_lock:
                    raw_values = self.client.read_input_registers(start, count)
                for offset, raw in enumerate(raw_values):
                    reg = REGISTERS.get(start + offset)
                    if reg is not None:
                        value = reg.decode(raw)
                        store.measurement(timestamp, reg, raw, value)
                        values[start + offset] = value
            except Exception as exc:
                # Optional blocks differ between WPM generations. Persist the
                # failed read so an older successful value cannot look live.
                for address in range(start, start + count):
                    reg = REGISTERS.get(address)
                    if reg is not None:
                        store.measurement(timestamp, reg, None, None, str(exc))

        status = values.get(2501)
        if status is not None:
            self._process_status(store, timestamp, status)

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
        with self.database_lock:
            self.restore_open_run(store)
        try:
            while not self.stop_event.is_set():
                started = time.monotonic()
                try:
                    with self.database_lock:
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
