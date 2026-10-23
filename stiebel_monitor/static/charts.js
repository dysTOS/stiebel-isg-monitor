export const STATUS_STATES = [
  {label: 'Verdichter', bit: 6, color: '#a7e22e'},
  {label: 'Heizen', bit: 4, color: '#ffb454'},
  {label: 'Warmwasser', bit: 5, color: '#65d8d2'},
  {label: 'HK-Pumpe', bit: 0, color: '#67aaf9'},
  {label: 'Heizstab', bit: 3, color: '#ff6b6b'},
  {label: 'Sommer', bit: 7, color: '#f1c75b'},
  {label: 'Abtauen', bit: 9, color: '#bd93f9'},
];

function setupCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  const context = canvas.getContext('2d');
  context.scale(dpr, dpr);
  return {context, width: rect.width, height: rect.height};
}

function nearestPoint(points, target) {
  let nearest = null;
  for (const point of points) {
    const timestamp = Date.parse(point.timestamp_utc);
    if (!nearest || Math.abs(timestamp - target) < Math.abs(nearest.timestamp - target)) {
      nearest = {timestamp, point};
    }
  }
  return nearest;
}

export function renderTemperatureChart({canvas, empty, tooltip, rows, colors, labels, bucketSeconds, hours, unit = '°C', formatValue}) {
  empty.style.display = rows.length ? 'none' : 'grid';
  tooltip.style.display = 'none';
  canvas.onpointermove = null;
  canvas.onpointerleave = null;
  const {context, width, height} = setupCanvas(canvas);
  if (!rows.length) {
    context.clearRect(0, 0, width, height);
    return;
  }
  const padding = {left: 58, right: 15, top: 12, bottom: 28};
  const groups = new Map();
  for (const row of rows) {
    if (!groups.has(row.name)) groups.set(row.name, []);
    groups.get(row.name).push(row);
  }
  const times = rows.map(row => Date.parse(row.timestamp_utc));
  const values = rows.map(row => row.value);
  let minTime = Math.min(...times);
  let maxTime = Math.max(...times);
  if (minTime === maxTime) maxTime += 1;
  const valuePadding = unit === '°C' ? 2 : Math.max(0.05, (Math.max(...values) - Math.min(...values)) * 0.08);
  const precision = unit === '°C' ? 0 : 2;
  const valueScale = 10 ** precision;
  const minValue = Math.floor((Math.min(...values) - valuePadding) * valueScale) / valueScale;
  const maxValue = Math.ceil((Math.max(...values) + valuePadding) * valueScale) / valueScale;
  const x = value => padding.left + (value - minTime) / (maxTime - minTime) * (width - padding.left - padding.right);
  const y = value => height - padding.bottom - (value - minValue) / (maxValue - minValue) * (height - padding.top - padding.bottom);
  const tolerance = Math.max(90_000, bucketSeconds * 1_500);

  function draw(hoverTime = null) {
    context.clearRect(0, 0, width, height);
    context.font = '11px system-ui';
    context.lineWidth = 1;
    context.strokeStyle = '#2a3233';
    context.fillStyle = '#7f8986';
    context.textAlign = 'right';
    for (let index = 0; index < 5; index += 1) {
      const value = minValue + (maxValue - minValue) * index / 4;
      const position = y(value);
      context.beginPath();
      context.moveTo(padding.left, position);
      context.lineTo(width - padding.right, position);
      context.stroke();
      context.fillText(`${value.toFixed(precision)} ${unit}`, padding.left - 8, position + 4);
    }
    context.textAlign = 'center';
    for (let index = 0; index < 4; index += 1) {
      const timestamp = minTime + (maxTime - minTime) * index / 3;
      const label = hours > 24
        ? new Date(timestamp).toLocaleString('de-AT', {day: '2-digit', month: '2-digit', hour: '2-digit'})
        : new Date(timestamp).toLocaleTimeString('de-AT', {hour: '2-digit', minute: '2-digit'});
      context.fillText(label, x(timestamp), height - 7);
    }
    for (const [name, points] of groups) {
      context.strokeStyle = colors[name];
      context.lineWidth = 2;
      context.beginPath();
      points.forEach((point, index) => {
        const pointX = x(Date.parse(point.timestamp_utc));
        const pointY = y(point.value);
        if (index) context.lineTo(pointX, pointY); else context.moveTo(pointX, pointY);
      });
      context.stroke();
      if (hoverTime != null) {
        const nearest = nearestPoint(points, hoverTime);
        if (nearest && Math.abs(nearest.timestamp - hoverTime) <= tolerance) {
          context.fillStyle = colors[name];
          context.beginPath();
          context.arc(x(nearest.timestamp), y(nearest.point.value), 3.5, 0, Math.PI * 2);
          context.fill();
        }
      }
    }
    if (hoverTime != null) {
      context.save();
      context.setLineDash([4, 4]);
      context.strokeStyle = '#d5ddd5';
      context.beginPath();
      context.moveTo(x(hoverTime), padding.top);
      context.lineTo(x(hoverTime), height - padding.bottom);
      context.stroke();
      context.restore();
    }
  }

  draw();
  canvas.onpointermove = event => {
    const rect = canvas.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;
    const requestedTime = minTime + Math.max(0, Math.min(1, (mouseX - padding.left) / (width - padding.left - padding.right))) * (maxTime - minTime);
    const nearest = nearestPoint(rows, requestedTime);
    if (!nearest) return;
    const hoverTime = nearest.timestamp;
    draw(hoverTime);

    tooltip.replaceChildren();
    const heading = document.createElement('strong');
    heading.textContent = new Date(hoverTime).toLocaleString('de-AT', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
    tooltip.append(heading);
    for (const [name, points] of groups) {
      const point = nearestPoint(points, hoverTime);
      const line = document.createElement('span');
      const marker = document.createElement('i');
      marker.style.background = colors[name];
      const value = document.createElement('b');
      value.textContent = point && Math.abs(point.timestamp - hoverTime) <= tolerance ? formatValue(point.point.value, unit, precision) : '–';
      line.append(marker, `${labels[name]} `, value);
      tooltip.append(line);
    }
    tooltip.style.display = 'block';
    tooltip.style.left = `${Math.max(8, Math.min(width - tooltip.offsetWidth - 8, mouseX + 14))}px`;
    tooltip.style.top = `${Math.max(8, Math.min(height - tooltip.offsetHeight - 8, mouseY + 12))}px`;
  };
  canvas.onpointerleave = () => {
    tooltip.style.display = 'none';
    draw();
  };
}

export function renderBarChart({canvas, empty, rows}) {
  empty.style.display = rows.length ? 'none' : 'grid';
  if (!rows.length) return;
  const {context, width, height} = setupCanvas(canvas);
  const padding = {left: 25, right: 8, top: 12, bottom: 30};
  const maximum = Math.max(1, ...rows.map(row => row.starts));
  const barWidth = (width - padding.left - padding.right) / rows.length;
  context.font = '11px system-ui';
  rows.forEach((row, index) => {
    const barHeight = (height - padding.top - padding.bottom) * row.starts / maximum;
    const left = padding.left + index * barWidth + barWidth * 0.15;
    const top = height - padding.bottom - barHeight;
    context.fillStyle = '#a7e22e';
    context.fillRect(left, top, barWidth * 0.7, barHeight);
    context.fillStyle = '#7f8986';
    context.textAlign = 'center';
    if (rows.length <= 10 || index % Math.ceil(rows.length / 8) === 0) context.fillText(row.day.slice(5), left + barWidth * 0.35, height - 8);
    if (row.starts) context.fillText(row.starts, left + barWidth * 0.35, top - 5);
  });
}

export function renderStateChart({canvas, empty, rows, hours}) {
  empty.style.display = rows.length ? 'none' : 'grid';
  const {context, width, height} = setupCanvas(canvas);
  context.clearRect(0, 0, width, height);
  if (!rows.length) return;

  const states = STATUS_STATES;
  const padding = {left: 100, right: 15, top: 12, bottom: 28};
  const times = rows.map(row => Date.parse(row.timestamp_utc));
  const minTime = Math.min(...times);
  let maxTime = Math.max(...times);
  if (minTime === maxTime) maxTime += 1;
  const x = timestamp => padding.left + (timestamp - minTime) / (maxTime - minTime) * (width - padding.left - padding.right);
  const laneHeight = (height - padding.top - padding.bottom) / states.length;

  context.font = '11px system-ui';
  context.textAlign = 'right';
  context.textBaseline = 'middle';
  states.forEach((state, index) => {
    const y = padding.top + laneHeight * (index + 0.5);
    context.fillStyle = state.color;
    context.fillText(state.label, padding.left - 10, y);
  });

  context.textAlign = 'center';
  context.textBaseline = 'alphabetic';
  for (let index = 0; index < 4; index += 1) {
    const timestamp = minTime + (maxTime - minTime) * index / 3;
    const label = hours > 24
      ? new Date(timestamp).toLocaleString('de-AT', {day: '2-digit', month: '2-digit', hour: '2-digit'})
      : new Date(timestamp).toLocaleTimeString('de-AT', {hour: '2-digit', minute: '2-digit'});
    context.fillText(label, x(timestamp), height - 7);
  }

  rows.forEach(row => {
    const status = row.operating_status == null ? null : Number(row.operating_status);
    states.forEach((state, index) => {
      const active = state.label === 'HK-Pumpe' && row.heating_circuit_pump_1 != null
        ? Boolean(row.heating_circuit_pump_1)
        : status == null ? false : Boolean(status & (1 << state.bit));
      if (!active) return;
      const y = padding.top + laneHeight * (index + 0.5);
      context.fillStyle = state.color;
      context.beginPath();
      context.arc(x(Date.parse(row.timestamp_utc)), y, 2.5, 0, Math.PI * 2);
      context.fill();
    });
  });
}

export function renderEnergyHistoryChart({canvas, empty, tooltip, rows, visible = {heatHeating: true, heatDhw: true, electricHeating: true, electricDhw: true, cop: true}}) {
  empty.style.display = rows.length ? 'none' : 'grid';
  tooltip.style.display = 'none';
  canvas.onpointermove = null;
  canvas.onpointerleave = null;
  const {context, width, height} = setupCanvas(canvas);
  context.clearRect(0, 0, width, height);
  if (!rows.length) return;

  const padding = {left: 48, right: 48, top: 20, bottom: 30};
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const sums = (row, names) => names.filter(name => visible[name]).reduce((sum, name) => sum + (row[name] ?? 0), 0);
  const heatNames = ['heatHeating', 'heatDhw'];
  const electricNames = ['electricHeating', 'electricDhw'];
  const maxEnergy = Math.max(1, ...rows.flatMap(row => [sums(row, heatNames), sums(row, electricNames)]));
  const energyMax = Math.max(1, Math.ceil(maxEnergy / 5) * 5);
  const copValues = visible.cop ? rows.map(row => row.cop).filter(value => Number.isFinite(value)) : [];
  let copMin = copValues.length ? Math.max(0, Math.floor(Math.min(...copValues) - 0.5)) : 0;
  let copMax = copValues.length ? Math.ceil(Math.max(...copValues) + 0.5) : 1;
  if (copMax <= copMin) copMax = copMin + 1;
  const yEnergy = value => padding.top + plotHeight * (1 - value / energyMax);
  const yCop = value => padding.top + plotHeight * (1 - (value - copMin) / (copMax - copMin));
  const groupWidth = plotWidth / rows.length;
  const barWidth = Math.min(18, groupWidth * 0.24);
  const gap = Math.min(5, groupWidth * 0.08);

  context.font = '11px system-ui';
  context.textBaseline = 'middle';
  context.textAlign = 'right';
  context.fillStyle = '#7f8986';
  context.strokeStyle = '#2a3233';
  context.lineWidth = 1;
  for (let tick = 0; tick <= 4; tick += 1) {
    const value = energyMax * tick / 4;
    const y = yEnergy(value);
    context.beginPath();
    context.moveTo(padding.left, y);
    context.lineTo(width - padding.right, y);
    context.stroke();
    context.fillText(tick === 0 ? '0 kWh' : value.toFixed(0), padding.left - 7, y);
    if (visible.cop) {
      context.textAlign = 'left';
      const copTick = (copMin + (copMax - copMin) * tick / 4).toFixed(tick === 0 ? 0 : 1);
      context.fillText(tick === 0 ? `${copTick} COP` : copTick, width - padding.right + 7, y);
    }
    context.textAlign = 'right';
  }
  context.textBaseline = 'alphabetic';

  const drawStack = (x, values, colors) => {
    let bottom = 0;
    values.forEach((value, index) => {
      if (value == null || value <= 0) return;
      const top = bottom + value;
      context.fillStyle = colors[index];
      context.fillRect(x, yEnergy(top), barWidth, Math.max(0, yEnergy(bottom) - yEnergy(top)));
      bottom = top;
    });
  };
  const copPoints = [];
  rows.forEach((row, index) => {
    const center = padding.left + groupWidth * (index + 0.5);
    drawStack(center - gap / 2 - barWidth, heatNames.map(name => visible[name] ? row[name] : null), ['#a7e22e', '#d9f99d']);
    drawStack(center + gap / 2, electricNames.map(name => visible[name] ? row[name] : null), ['#67aaf9', '#65d8d2']);
    if (visible.cop && row.cop != null) copPoints.push({x: center, y: yCop(row.cop), value: row.cop});
    if (rows.length <= 10 || index % Math.ceil(rows.length / 8) === 0) {
      context.fillStyle = '#7f8986';
      context.textAlign = 'center';
      context.fillText(new Date(`${row.day}T12:00:00`).toLocaleDateString('de-AT', {day: '2-digit', month: '2-digit'}), center, height - 7);
    }
  });

  if (copPoints.length) {
    context.strokeStyle = '#ffb454';
    context.fillStyle = '#ffb454';
    context.lineWidth = 2;
    context.beginPath();
    copPoints.forEach((point, index) => index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y));
    context.stroke();
    copPoints.forEach(point => {
      context.beginPath();
      context.arc(point.x, point.y, 3, 0, Math.PI * 2);
      context.fill();
    });
  }

  canvas.onpointermove = event => {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const index = Math.floor((x - padding.left) / groupWidth);
    if (index < 0 || index >= rows.length) {
      tooltip.style.display = 'none';
      return;
    }
    const row = rows[index];
    const day = new Date(`${row.day}T12:00:00`).toLocaleDateString('de-AT', {day: '2-digit', month: '2-digit', year: 'numeric'});
    const value = number => number == null ? '–' : Number(number).toLocaleString('de-AT', {maximumFractionDigits: 1});
    const cop = row.cop == null ? '–' : Number(row.cop).toLocaleString('de-AT', {maximumFractionDigits: 2});
    const details = [
      ['heatHeating', 'Wärme Heizen', '#a7e22e', value(row.heatHeating), 'kWh'],
      ['heatDhw', 'Wärme Warmwasser', '#d9f99d', value(row.heatDhw), 'kWh'],
      ['electricHeating', 'Strom Heizen', '#67aaf9', value(row.electricHeating), 'kWh'],
      ['electricDhw', 'Strom Warmwasser', '#65d8d2', value(row.electricDhw), 'kWh'],
      ['cop', 'COP', '#ffb454', cop, ''],
    ].filter(([name]) => visible[name]);
    tooltip.innerHTML = `<strong>${day}</strong>${details.map(([, label, color, result, unit]) => `<span><i style="background:${color}"></i>${label} <b>${result}${unit ? ` ${unit}` : ''}</b></span>`).join('')}`;
    tooltip.style.display = 'block';
    const wrapper = canvas.parentElement.getBoundingClientRect();
    tooltip.style.left = `${Math.min(wrapper.width - tooltip.offsetWidth - 8, Math.max(8, event.clientX - wrapper.left + 12))}px`;
    tooltip.style.top = `${Math.min(wrapper.height - tooltip.offsetHeight - 8, Math.max(8, event.clientY - wrapper.top + 12))}px`;
  };
  canvas.onpointerleave = () => { tooltip.style.display = 'none'; };
}
