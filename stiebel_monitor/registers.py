from dataclasses import dataclass

UNAVAILABLE = 32768

@dataclass(frozen=True)
class Register:
    address: int
    name: str
    unit: str | None = None
    scale: float = 1.0
    signed: bool = False
    category: str = "status"

    def decode(self, raw: int) -> float | int | None:
        if raw == UNAVAILABLE:
            return None
        value = raw - 65536 if self.signed and raw >= 32768 else raw
        return value * self.scale if self.scale != 1 else value

# Input registers, 1-based addresses as printed by Stiebel Eltron.
REGISTERS = {
    507: Register(507, "outside_temperature", "°C", 0.1, True, "temperature"),
    501: Register(501, "room_temperature_hc1", "°C", 0.1, True, "temperature"),
    508: Register(508, "actual_temperature_hc1", "°C", 0.1, True, "temperature"),
    509: Register(509, "set_temperature_hc1", "°C", 0.1, True, "temperature"),
    510: Register(510, "set_temperature_hc1_alt", "°C", 0.1, True, "temperature"),
    511: Register(511, "room_temperature_hc2", "°C", 0.1, True, "temperature"),
    512: Register(512, "set_temperature_hc2", "°C", 0.1, True, "temperature"),
    513: Register(513, "heat_pump_flow_temperature", "°C", 0.1, True, "temperature"),
    515: Register(515, "flow_temperature", "°C", 0.1, True, "temperature"),
    516: Register(516, "return_temperature", "°C", 0.1, True, "temperature"),
    518: Register(518, "buffer_temperature", "°C", 0.1, True, "temperature"),
    519: Register(519, "buffer_set_temperature", "°C", 0.1, True, "temperature"),
    520: Register(520, "heating_pressure", "bar", 0.01, False, "hydraulic"),
    521: Register(521, "flow_rate", "l/min", 0.1, False, "hydraulic"),
    522: Register(522, "dhw_temperature", "°C", 0.1, True, "temperature"),
    523: Register(523, "dhw_set_temperature", "°C", 0.1, True, "temperature"),
    542: Register(542, "heat_pump_return_temperature", "°C", 0.1, True, "temperature"),
    543: Register(543, "heat_pump_flow_temperature_1", "°C", 0.1, True, "temperature"),
    544: Register(544, "hot_gas_temperature", "°C", 0.1, True, "temperature"),
    545: Register(545, "low_pressure", "bar", 0.01, False, "hydraulic"),
    546: Register(546, "mean_pressure", "bar", 0.01, False, "hydraulic"),
    547: Register(547, "high_pressure", "bar", 0.01, False, "hydraulic"),
    548: Register(548, "heat_pump_flow_rate", "l/min", 0.1, False, "hydraulic"),
    2501: Register(2501, "operating_status", category="status"),
    2504: Register(2504, "fault_status", category="status"),
    2505: Register(2505, "can_bus_status", category="status"),
    3501: Register(3501, "heat_energy_heating_day", "kWh", category="energy"),
    3502: Register(3502, "heat_energy_heating_total", "kWh", category="energy"),
    3503: Register(3503, "heat_energy_heating_total_mwh", "MWh", category="energy"),
    3504: Register(3504, "heat_energy_dhw_day", "kWh", category="energy"),
    3505: Register(3505, "heat_energy_dhw_total", "kWh", category="energy"),
    3506: Register(3506, "heat_energy_dhw_total_mwh", "MWh", category="energy"),
    3507: Register(3507, "heat_energy_booster_heating_total", "kWh", category="energy"),
    3508: Register(3508, "heat_energy_booster_heating_total_mwh", "MWh", category="energy"),
    3509: Register(3509, "heat_energy_booster_dhw_total", "kWh", category="energy"),
    3510: Register(3510, "heat_energy_booster_dhw_total_mwh", "MWh", category="energy"),
    3511: Register(3511, "electric_energy_heating_day", "kWh", category="energy"),
    3512: Register(3512, "electric_energy_heating_total", "kWh", category="energy"),
    3513: Register(3513, "electric_energy_heating_total_mwh", "MWh", category="energy"),
    3514: Register(3514, "electric_energy_dhw_day", "kWh", category="energy"),
    3515: Register(3515, "electric_energy_dhw_total", "kWh", category="energy"),
    3516: Register(3516, "electric_energy_dhw_total_mwh", "MWh", category="energy"),
    3517: Register(3517, "compressor_heating_hours", "h", category="counter"),
    3518: Register(3518, "compressor_dhw_hours", "h", category="counter"),
    3519: Register(3519, "compressor_cooling_hours", "h", category="counter"),
    3520: Register(3520, "booster_1_hours", "h", category="counter"),
    3521: Register(3521, "booster_2_hours", "h", category="counter"),
    3539: Register(3539, "compressor_heating_hours_hp1", "h", category="counter"),
    3542: Register(3542, "compressor_dhw_hours_hp1", "h", category="counter"),
    3545: Register(3545, "compressor_cooling_hours_hp1", "h", category="counter"),
    3546: Register(3546, "booster_1_hours_hp1", "h", category="counter"),
    3547: Register(3547, "booster_2_hours_hp1", "h", category="counter"),
    2502: Register(2502, "power_off_status", category="status"),
    2503: Register(2503, "component_status", category="status"),
}

STATUS_BITS = {"heating": 4, "dhw": 5, "compressor": 6}
READ_REGISTERS = tuple(REGISTERS)

# Inclusive ranges. Reading blocks is much lighter on the ISG than opening one
# TCP connection for every individual register.
READ_BLOCKS = ((501, 23), (542, 7), (2501, 5), (3501, 21), (3539, 9))
