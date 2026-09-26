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
    profile: str = "WPM"

    def decode(self, raw: int) -> float | int | None:
        if raw == UNAVAILABLE:
            return None
        value = raw - 65536 if self.signed and raw >= 32768 else raw
        return value * self.scale if self.scale != 1 else value

# Input registers, 1-based addresses as printed by Stiebel Eltron.
REGISTERS = {
    501: Register(501, "room_temperature_hc1", "°C", 0.1, True, "temperature"),
    502: Register(502, "room_set_temperature_fe7", "°C", 0.1, True, "temperature"),
    503: Register(503, "room_temperature_fek", "°C", 0.1, True, "temperature"),
    504: Register(504, "room_set_temperature_fek", "°C", 0.1, True, "temperature"),
    505: Register(505, "room_humidity", "%", 0.1, False, "climate"),
    506: Register(506, "dew_point_temperature", "°C", 0.1, True, "temperature"),
    507: Register(507, "outside_temperature", "°C", 0.1, True, "temperature"),
    508: Register(508, "actual_temperature_hc1", "°C", 0.1, True, "temperature"),
    509: Register(509, "set_temperature_hc1", "°C", 0.1, True, "temperature"),
    510: Register(510, "set_temperature_hc1_alt", "°C", 0.1, True, "temperature"),
    511: Register(511, "room_temperature_hc2", "°C", 0.1, True, "temperature"),
    512: Register(512, "set_temperature_hc2", "°C", 0.1, True, "temperature"),
    513: Register(513, "heat_pump_flow_temperature", "°C", 0.1, True, "temperature"),
    514: Register(514, "booster_flow_temperature", "°C", 0.1, True, "temperature"),
    515: Register(515, "flow_temperature", "°C", 0.1, True, "temperature"),
    516: Register(516, "return_temperature", "°C", 0.1, True, "temperature"),
    517: Register(517, "fixed_set_temperature", "°C", 0.1, True, "temperature"),
    518: Register(518, "buffer_temperature", "°C", 0.1, True, "temperature"),
    519: Register(519, "buffer_set_temperature", "°C", 0.1, True, "temperature"),
    520: Register(520, "heating_pressure", "bar", 0.01, False, "hydraulic"),
    521: Register(521, "flow_rate", "l/min", 0.1, False, "hydraulic"),
    522: Register(522, "dhw_temperature", "°C", 0.1, True, "temperature"),
    523: Register(523, "dhw_set_temperature", "°C", 0.1, True, "temperature"),
    524: Register(524, "fan_cooling_temperature", "°C", 0.1, True, "temperature"),
    525: Register(525, "fan_cooling_set_temperature", "°C", 0.1, True, "temperature"),
    526: Register(526, "surface_cooling_temperature", "°C", 0.1, True, "temperature"),
    527: Register(527, "surface_cooling_set_temperature", "°C", 0.1, True, "temperature"),
    528: Register(528, "solar_collector_temperature", "°C", 0.1, True, "temperature"),
    529: Register(529, "solar_storage_temperature", "°C", 0.1, True, "temperature"),
    530: Register(530, "solar_runtime", "h", category="counter"),
    531: Register(531, "external_heat_source_temperature", "°C", 0.1, True, "temperature"),
    532: Register(532, "external_heat_source_set_temperature", "K", 0.1, True, "temperature"),
    533: Register(533, "heating_application_limit", "°C", 0.1, True, "temperature"),
    534: Register(534, "dhw_application_limit", "°C", 0.1, True, "temperature"),
    535: Register(535, "external_heat_source_runtime", "h", category="counter"),
    536: Register(536, "source_temperature", "°C", 0.1, True, "temperature"),
    537: Register(537, "source_min_temperature", "°C", 0.1, True, "temperature"),
    538: Register(538, "source_pressure", "bar", 0.01, True, "hydraulic"),
    539: Register(539, "system_hot_gas_temperature", "°C", 0.1, True, "temperature"),
    540: Register(540, "system_high_pressure", "bar", 0.1, True, "hydraulic"),
    541: Register(541, "system_low_pressure", "bar", 0.1, True, "hydraulic"),
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
    3644: Register(3644, "compressor_heating_hours_wpm_system_hp1", "h", category="counter", profile="WPMsystem"),
    3645: Register(3645, "compressor_dhw_hours_wpm_system_hp1", "h", category="counter", profile="WPMsystem"),
    2502: Register(2502, "power_off_status", category="status"),
    2503: Register(2503, "component_status", category="status"),
}

STATUS_BITS = {"heating": 4, "dhw": 5, "compressor": 6}

# Inclusive ranges. Reading blocks is much lighter on the ISG than opening one
# TCP connection for every individual register.
READ_BLOCKS = ((501, 23), (542, 7), (2501, 5), (3501, 21), (3539, 9))

# WPMsystem exposes room-control values in this additional input-register block.
# WPM 3/3i installations may not implement it, so the monitor reads it as optional.
for address, name in (
    (584, "room_temperature_hc1_wpm_system"), (585, "room_set_temperature_hc1_wpm_system"),
    (586, "room_humidity_hc1_wpm_system"), (587, "room_dew_point_hc1_wpm_system"),
    (588, "room_temperature_hc2_wpm_system"), (589, "room_set_temperature_hc2_wpm_system"),
    (590, "room_humidity_hc2_wpm_system"), (591, "room_dew_point_hc2_wpm_system"),
    (592, "room_temperature_hc3_wpm_system"), (593, "room_set_temperature_hc3_wpm_system"),
    (594, "room_humidity_hc3_wpm_system"), (595, "room_dew_point_hc3_wpm_system"),
    (596, "room_temperature_hc4_wpm_system"), (597, "room_set_temperature_hc4_wpm_system"),
    (598, "room_humidity_hc4_wpm_system"), (599, "room_dew_point_hc4_wpm_system"),
    (600, "room_temperature_hc5_wpm_system"), (601, "room_set_temperature_hc5_wpm_system"),
    (602, "room_humidity_hc5_wpm_system"), (603, "room_dew_point_hc5_wpm_system"),
):
    category = "climate" if "humidity" in name else "temperature"
    REGISTERS[address] = Register(address, name, "°C" if category == "temperature" else "%", 0.1, category == "temperature", category, "WPMsystem")

for heat_pump in range(2, 7):
    start = 549 + (heat_pump - 2) * 7
    for offset, (suffix, unit, scale, signed, category) in enumerate((
        ("return_temperature", "°C", 0.1, True, "temperature"),
        ("flow_temperature", "°C", 0.1, True, "temperature"),
        ("hot_gas_temperature", "°C", 0.1, True, "temperature"),
        ("low_pressure", "bar", 0.01, True, "hydraulic"),
        ("mean_pressure", "bar", 0.01, True, "hydraulic"),
        ("high_pressure", "bar", 0.01, True, "hydraulic"),
        ("flow_rate", "l/min", 0.1, False, "hydraulic"),
    )):
        address = start + offset
        REGISTERS[address] = Register(address, f"heat_pump_{heat_pump}_{suffix}", unit, scale, signed, category, "Kaskade")

for circuit in range(1, 6):
    address = 604 + circuit - 1
    REGISTERS[address] = Register(address, f"cooling_room_set_temperature_{circuit}", "°C", 0.1, True, "temperature", "WPMsystem")

REGISTERS[609] = Register(609, "wpm3i_flow_temperature", "°C", 0.1, True, "temperature", "WPM 3i")
for circuit in range(3, 6):
    actual_address = 610 + (circuit - 3) * 2
    REGISTERS[actual_address] = Register(actual_address, f"actual_temperature_hc{circuit}", "°C", 0.1, True, "temperature", "WPMsystem")
    REGISTERS[actual_address + 1] = Register(actual_address + 1, f"set_temperature_hc{circuit}", "°C", 0.1, True, "temperature", "WPMsystem")

OPTIONAL_READ_BLOCKS = ((524, 18), (584, 20), (609, 7), (3644, 2))
ON_DEMAND_READ_BLOCKS = ((501, 48), (549, 35), (584, 32), (2501, 5), (3501, 21), (3539, 9), (3644, 2))
READ_REGISTERS = tuple(REGISTERS)
