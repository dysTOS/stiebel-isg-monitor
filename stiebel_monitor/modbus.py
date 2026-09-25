import socket
import struct
from dataclasses import dataclass

class ModbusError(Exception): pass

@dataclass
class ModbusTCP:
    host: str
    port: int = 502
    unit_id: int = 1
    timeout: float = 5.0

    def read_input_registers(self, address: int, count: int = 1) -> list[int]:
        if not 1 <= address <= 65536 or count < 1 or address + count - 1 > 65536:
            raise ValueError("Modbus-Adresse/Anzahl außerhalb des gültigen Bereichs")
        # ISG documentation uses 1-based addresses; Modbus PDU uses 0-based offsets.
        pdu_address = address - 1
        transaction = getattr(self, "_transaction", 0) + 1
        self._transaction = transaction & 0xffff
        request = struct.pack(">HHHBBHH", self._transaction, 0, 6, self.unit_id, 4, pdu_address, count)
        with socket.create_connection((self.host, self.port), self.timeout) as sock:
            sock.sendall(request)
            # MBAP (7 bytes) + unit id + function + byte count.
            header = self._recv_exact(sock, 9)
            tid, protocol, length, unit, function, byte_count = struct.unpack(">HHHBBB", header)
            if tid != self._transaction or protocol != 0 or unit != self.unit_id:
                raise ModbusError("Ungültige Modbus-TCP-Antwort")
            if function & 0x80:
                # For an exception response the byte after the function code
                # is already contained in the seven-byte header read above.
                raise ModbusError(f"Modbus-Exception {byte_count}")
            if function != 4 or byte_count != count * 2:
                raise ModbusError("Unerwartete Registerantwort")
            return list(struct.unpack(f">{count}H", self._recv_exact(sock, byte_count)))

    @staticmethod
    def _recv_exact(sock, count):
        data = b""
        while len(data) < count:
            chunk = sock.recv(count - len(data))
            if not chunk: raise ModbusError("Verbindung vor vollständiger Antwort beendet")
            data += chunk
        return data
