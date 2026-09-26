import {renderBarChart, renderTemperatureChart} from '/charts.js';

const COLORS = {
  outside_temperature: '#67aaf9', room_temperature_hc1: '#f1c75b', room_temperature_fek: '#e78ac3',
  room_temperature_hc1_wpm_system: '#f1c75b', actual_temperature_hc1: '#a7e22e',
  heat_pump_flow_temperature: '#ffb454', return_temperature: '#bd93f9', buffer_temperature: '#65d8d2',
  dhw_temperature: '#ff6b6b',
};
const LABELS = {
  outside_temperature: 'Außen', room_temperature_hc1: 'Raumfühler FE7', room_temperature_fek: 'Raumfühler FEK',
  room_temperature_hc1_wpm_system: 'Raum HK 1', actual_temperature_hc1: 'Heizkreis',
  heat_pump_flow_temperature: 'Vorlauf WP', return_temperature: 'Rücklauf', buffer_temperature: 'Puffer',
  dhw_temperature: 'Warmwasser',
};
const ENERGY_NAMES = ['heat_energy_heating_day', 'heat_energy_dhw_day', 'electric_energy_heating_day', 'electric_energy_dhw_day'];
const $ = id => document.getElementById(id);
let payload = null;
let loading = false;

const fmt = (value, unit = '', digits = 1) => value == null ? '–' : `${Number(value).toLocaleString('de-DE', {maximumFractionDigits: digits, minimumFractionDigits: digits})}${unit ? ` ${unit}` : ''}`;
const date = value => value ? new Date(value).toLocaleString('de-AT', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'}) : '–';
const latestEntry = name => payload.latest.find(item => item.name === name) || null;
const dataAge = timestamp => Date.parse(payload.generated_at) - Date.parse(timestamp);
const entryIsFresh = entry => Boolean(entry && !entry.error && entry.value != null && dataAge(entry.timestamp_utc) <= payload.stale_after_seconds * 1000);
const latest = name => entryIsFresh(latestEntry(name)) ? latestEntry(name).value : null;
const firstEntry = (...names) => names.map(latestEntry).find(entryIsFresh) || null;
const setText = (id, value) => { $(id).textContent = value; };

function ageLabel(entry) {
  if (!entry) return 'Nicht erfasst';
  if (entry.error) return 'Lesefehler';
  if (entry.value == null) return entry.raw_value === 32768 ? 'Nicht verfügbar' : 'Kein Wert';
  const seconds = Math.max(0, Math.round(dataAge(entry.timestamp_utc) / 1000));
  if (seconds > payload.stale_after_seconds) return `Veraltet · ${date(entry.timestamp_utc)}`;
  if (seconds < 90) return 'Gerade gemessen';
  return `Vor ${Math.round(seconds / 60)} min`;
}

function chip(label, active, warn = false) {
  const element = document.createElement('span');
  element.className = `chip ${active ? (warn ? 'warn' : 'active') : ''}`;
  element.textContent = label;
  return element;
}

function renderCards() {
  const outside = latestEntry('outside_temperature');
  const room = firstEntry('room_temperature_hc1_wpm_system', 'room_temperature_hc1', 'room_temperature_fek');
  const flow = firstEntry('flow_temperature', 'heat_pump_flow_temperature', 'heat_pump_flow_temperature_1');
  const dhw = latestEntry('dhw_temperature');
  setText('outside', fmt(entryIsFresh(outside) ? outside.value : null, '°C'));
  setText('outside-meta', `Außentemperatur · ${ageLabel(outside)}`);
  setText('room', fmt(room?.value, '°C'));
  setText('room-meta', `${room ? LABELS[room.name] : 'Raumtemperatur'} · ${ageLabel(room)}`);
  setText('flow', fmt(flow?.value, '°C'));
  setText('delta', `Differenz ${flow && latest('return_temperature') != null ? fmt(flow.value - latest('return_temperature'), 'K') : '–'} · ${ageLabel(flow)}`);
  setText('dhw', fmt(entryIsFresh(dhw) ? dhw.value : null, '°C'));
  setText('dhw-set', `Soll ${fmt(latest('dhw_set_temperature'), '°C')} · ${ageLabel(dhw)}`);

  const status = Number(latest('operating_status') || 0);
  const chips = $('status-chips');
  chips.replaceChildren();
  [['Verdichter', 6], ['Heizen', 4], ['Warmwasser', 5], ['HK-Pumpe', 0], ['Heizstab', 3], ['Sommer', 7], ['Abtauen', 9]]
    .forEach(([label, bit]) => chips.append(chip(label, Boolean(status & (1 << bit)), label === 'Heizstab')));

  setText('starts-today', payload.today.starts);
  setText('average-runtime', payload.today.average_minutes != null ? `${payload.today.average_minutes} min` : '–');
  const energy = Object.fromEntries(ENERGY_NAMES.map(name => [name, latest(name)]));
  const complete = ENERGY_NAMES.every(name => energy[name] != null);
  const heat = complete ? energy.heat_energy_heating_day + energy.heat_energy_dhw_day : null;
  const power = complete ? energy.electric_energy_heating_day + energy.electric_energy_dhw_day : null;
  setText('cop', heat != null && power > 0 ? (heat / power).toFixed(2) : '–');
}

function renderTargets() {
  const box = $('targets');
  box.replaceChildren();
  const targets = [
    ['Heizkreis HK 1', ['actual_temperature_hc1'], ['set_temperature_hc1', 'set_temperature_hc1_alt']],
    ['Puffer', ['buffer_temperature'], ['buffer_set_temperature']],
    ['Warmwasser', ['dhw_temperature'], ['dhw_set_temperature']],
  ];
  for (const [label, actualNames, targetNames] of targets) {
    const actual = firstEntry(...actualNames);
    const target = firstEntry(...targetNames);
    const item = document.createElement('div');
    item.className = 'target-item';
    const title = document.createElement('span');
    title.textContent = label;
    const values = document.createElement('strong');
    values.textContent = `${fmt(actual?.value, '°C')} → ${fmt(target?.value, '°C')}`;
    const detail = document.createElement('small');
    detail.textContent = actual && target ? `Abweichung ${fmt(actual.value - target.value, 'K')} · ${ageLabel(actual)}` : 'Soll- oder Istwert nicht verfügbar';
    item.append(title, values, detail);
    box.append(item);
  }
}

function appendAlert(box, kind, title, detail) {
  const item = document.createElement('div');
  item.className = `alert-item ${kind}`;
  const marker = document.createElement('i');
  const content = document.createElement('div');
  const heading = document.createElement('strong');
  const description = document.createElement('small');
  heading.textContent = title;
  description.textContent = detail;
  content.append(heading, description);
  item.append(marker, content);
  box.append(item);
}

function renderAlerts() {
  const box = $('alerts-list');
  box.replaceChildren();
  const items = [];
  const successAge = payload.monitor.last_success ? dataAge(payload.monitor.last_success) : Infinity;
  if (!payload.monitor.connected || successAge > payload.stale_after_seconds * 1000) {
    items.push(['bad', 'Keine aktuelle Verbindung zum ISG', payload.monitor.last_success ? `Letzter Erfolg ${date(payload.monitor.last_success)}` : 'Noch keine erfolgreiche Messung']);
  }
  const fault = latest('fault_status');
  if (fault != null && Number(fault) !== 0) items.push(['bad', 'Fehlerstatus aktiv', `Registerwert ${fault} (0x${Number(fault).toString(16).toUpperCase()})`]);
  const visibleSeries = new Set(Object.keys(COLORS));
  payload.latest.filter(item => item.error && visibleSeries.has(item.name)).forEach(item => items.push(['warn', `Messfehler: ${LABELS[item.name] || item.name}`, item.error]));
  if (!items.length) items.push(['ok', 'Keine aktiven Hinweise', 'Fehlerstatus 0 und aktuelle Messwerte verfügbar']);
  items.slice(0, 8).forEach(item => appendAlert(box, ...item));
}

function renderEventHistory() {
  const box = $('events-list');
  box.replaceChildren();
  const events = [
    ...payload.events.map(item => ({timestamp: item.timestamp_utc, title: item.event, detail: item.detail || '–'})),
    ...payload.counter_events.map(item => ({timestamp: item.timestamp_utc, title: `Zähler: ${item.name}`, detail: `${item.previous} → ${item.current} (${item.event})`})),
  ].sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp)).slice(0, 6);
  if (!events.length) {
    const empty = document.createElement('small');
    empty.className = 'muted';
    empty.textContent = 'Noch keine Ereignisse gespeichert.';
    box.append(empty);
    return;
  }
  events.forEach(item => appendAlert(box, 'info', item.title, `${date(item.timestamp)} · ${item.detail}`));
}

function dailyEnergy(values) {
  const has = name => Object.prototype.hasOwnProperty.call(values, name) && values[name] != null;
  return {
    heat: has('heat_energy_heating_day') && has('heat_energy_dhw_day') ? Number(values.heat_energy_heating_day) + Number(values.heat_energy_dhw_day) : null,
    power: has('electric_energy_heating_day') && has('electric_energy_dhw_day') ? Number(values.electric_energy_heating_day) + Number(values.electric_energy_dhw_day) : null,
  };
}

function renderEnergyHistory() {
  const box = $('energy-history');
  box.replaceChildren();
  const byDay = {};
  payload.energy_daily.forEach(item => {
    if (!byDay[item.day]) byDay[item.day] = {};
    byDay[item.day][item.name] = item.value;
  });
  const days = Object.entries(byDay).sort(([left], [right]) => left.localeCompare(right)).slice(-14);
  if (!days.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-inline';
    empty.textContent = 'Noch keine Energiehistorie gespeichert';
    box.append(empty);
    return;
  }
  days.forEach(([day, values], index) => {
    const current = dailyEnergy(values);
    const previous = index ? dailyEnergy(days[index - 1][1]) : null;
    const item = document.createElement('div');
    item.className = 'history-item';
    const texts = [
      [document.createElement('strong'), new Date(`${day}T12:00:00`).toLocaleDateString('de-AT', {day: '2-digit', month: '2-digit'})],
      [document.createElement('span'), `Wärme ${fmt(current.heat, 'kWh')}`],
      [document.createElement('span'), `Strom ${fmt(current.power, 'kWh')}`],
      [document.createElement('span'), `COP ${current.heat != null && current.power > 0 ? (current.heat / current.power).toFixed(2) : '–'}`],
    ];
    texts.forEach(([element, text]) => { element.textContent = text; item.append(element); });
    const comparison = document.createElement('small');
    comparison.textContent = previous && current.heat != null && current.power != null && previous.heat != null && previous.power != null
      ? `ggü. Vortag: Wärme ${fmt(current.heat - previous.heat, 'kWh')} · Strom ${fmt(current.power - previous.power, 'kWh')}`
      : 'Kein vollständiger Vortagsvergleich';
    item.append(comparison);
    box.append(item);
  });
}

function renderCycling() {
  const complete = payload.runs.filter(run => run.complete && run.duration_seconds != null);
  const chronological = payload.runs.slice().sort((left, right) => Date.parse(left.started_utc) - Date.parse(right.started_utc));
  const pauses = [];
  for (let index = 1; index < chronological.length; index += 1) {
    const previous = chronological[index - 1];
    const current = chronological[index];
    if (previous.ended_utc && Date.parse(current.started_utc) >= Date.parse(previous.ended_utc)) pauses.push((Date.parse(current.started_utc) - Date.parse(previous.ended_utc)) / 60000);
  }
  const averagePause = pauses.length ? pauses.reduce((sum, value) => sum + value, 0) / pauses.length : null;
  const averageRun = complete.length ? complete.reduce((sum, run) => sum + run.duration_seconds / 60, 0) / complete.length : null;
  $('cycling-summary').innerHTML = `<span>Ø Laufzeit <strong>${averageRun == null ? '–' : `${averageRun.toFixed(0)} min`}</strong></span><span>Ø Pause <strong>${averagePause == null ? '–' : `${averagePause.toFixed(0)} min`}</strong></span><small>Aus den ${complete.length} vollständigen gespeicherten Läufen</small>`;
}

function renderCharts() {
  const rows = payload.series.filter(item => Object.prototype.hasOwnProperty.call(COLORS, item.name));
  const legend = $('temp-legend');
  legend.replaceChildren();
  [...new Set(rows.map(item => item.name))].forEach(name => {
    const item = document.createElement('span');
    const marker = document.createElement('i');
    marker.style.background = COLORS[name];
    item.append(marker, LABELS[name]);
    legend.append(item);
  });
  renderTemperatureChart({canvas: $('temperature-chart'), empty: $('temp-empty'), tooltip: $('temp-tooltip'), rows, colors: COLORS, labels: LABELS, bucketSeconds: payload.bucket_seconds, hours: payload.hours, formatValue: fmt});
  renderBarChart({canvas: $('starts-chart'), empty: $('starts-empty'), rows: payload.daily});
}

function renderEnergy() {
  const box = $('energy-cards');
  box.replaceChildren();
  [['Wärme Heizen', 'heat_energy_heating_day'], ['Wärme Warmwasser', 'heat_energy_dhw_day'], ['Strom Heizen', 'electric_energy_heating_day'], ['Strom Warmwasser', 'electric_energy_dhw_day']].forEach(([label, name]) => {
    const item = document.createElement('div');
    item.className = 'energy-item';
    const title = document.createElement('span');
    const value = document.createElement('strong');
    const age = document.createElement('small');
    title.textContent = label;
    value.textContent = fmt(latest(name), 'kWh');
    age.textContent = ageLabel(latestEntry(name));
    item.append(title, value, age);
    box.append(item);
  });
}

function renderRuns() {
  const body = $('runs');
  body.replaceChildren();
  payload.runs.forEach(run => {
    const row = document.createElement('tr');
    [date(run.started_utc) + (run.complete ? '' : ' *'), run.dhw ? 'Warmwasser' : run.heating ? 'Heizen' : 'Sonstiges', run.duration_seconds != null ? `${Math.round(run.duration_seconds / 60)} min` : '–'].forEach(value => {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.append(cell);
    });
    body.append(row);
  });
  if (!payload.runs.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 3;
    cell.textContent = 'Noch keine Verdichterläufe';
    row.append(cell);
    body.append(row);
  }
}

function renderDetails() {
  const box = $('details');
  box.replaceChildren();
  [['Rücklauf', ['return_temperature'], '°C'], ['Puffer', ['buffer_temperature'], '°C'], ['Puffer Soll', ['buffer_set_temperature'], '°C'], ['Volumenstrom', ['flow_rate', 'heat_pump_flow_rate'], 'l/min'], ['Heizungsdruck', ['heating_pressure'], 'bar'], ['Verdichter Heizen', ['compressor_heating_hours', 'compressor_heating_hours_hp1', 'compressor_heating_hours_wpm_system_hp1'], 'h'], ['Verdichter Warmwasser', ['compressor_dhw_hours', 'compressor_dhw_hours_hp1', 'compressor_dhw_hours_wpm_system_hp1'], 'h']].forEach(([label, names, unit]) => {
    const wrapper = document.createElement('div');
    const term = document.createElement('dt');
    const detail = document.createElement('dd');
    const entry = firstEntry(...names);
    const age = document.createElement('small');
    term.textContent = label;
    detail.textContent = fmt(entry?.value, unit, unit === 'bar' ? 2 : 1);
    age.textContent = ageLabel(entry || latestEntry(names[0]));
    detail.append(age);
    wrapper.append(term, detail);
    box.append(wrapper);
  });
}

function renderConnection() {
  const element = $('connection');
  const fresh = payload.monitor.last_success && dataAge(payload.monitor.last_success) <= payload.stale_after_seconds * 1000;
  const online = payload.monitor.connected && fresh;
  element.className = `connection ${online ? 'online' : 'offline'}`;
  element.querySelector('span').textContent = online ? 'ISG verbunden' : payload.monitor.polling ? 'Messung läuft' : 'ISG nicht aktuell';
  setText('updated', payload.monitor.last_success ? `Letzte Messung ${date(payload.monitor.last_success)} · ${payload.timezone}` : 'Noch keine erfolgreiche Messung');
}

function render() {
  renderConnection(); renderCards(); renderTargets(); renderAlerts(); renderEventHistory(); renderEnergyHistory();
  renderCycling(); renderCharts(); renderEnergy(); renderRuns(); renderDetails();
}

async function load() {
  if (loading) return;
  loading = true;
  try {
    const response = await fetch(`/api/dashboard?hours=${$('range').value}`, {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    payload = await response.json();
    render();
  } catch (error) {
    const connection = $('connection');
    connection.className = 'connection offline';
    connection.querySelector('span').textContent = 'Dashboard offline';
    console.error(error);
  } finally {
    loading = false;
  }
}

$('range').addEventListener('change', load);
window.addEventListener('resize', () => payload && renderCharts());
load();
setInterval(load, 30000);
