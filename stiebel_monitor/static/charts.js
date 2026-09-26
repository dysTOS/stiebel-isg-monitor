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

export function renderTemperatureChart({canvas, empty, tooltip, rows, colors, labels, bucketSeconds, hours, formatValue}) {
  empty.style.display = rows.length ? 'none' : 'grid';
  tooltip.style.display = 'none';
  canvas.onpointermove = null;
  canvas.onpointerleave = null;
  if (!rows.length) return;

  const {context, width, height} = setupCanvas(canvas);
  const padding = {left: 42, right: 15, top: 12, bottom: 28};
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
  const minValue = Math.floor(Math.min(...values) - 2);
  const maxValue = Math.ceil(Math.max(...values) + 2);
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
      context.fillText(`${value.toFixed(0)}°`, padding.left - 8, position + 4);
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
      value.textContent = point && Math.abs(point.timestamp - hoverTime) <= tolerance ? formatValue(point.point.value, '°C') : '–';
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
