const COLORS={outside_temperature:'#67aaf9',actual_temperature_hc1:'#a7e22e',heat_pump_flow_temperature:'#ffb454',return_temperature:'#bd93f9',buffer_temperature:'#65d8d2',dhw_temperature:'#ff6b6b'};
const LABELS={outside_temperature:'Außen',actual_temperature_hc1:'Heizkreis',heat_pump_flow_temperature:'Vorlauf WP',return_temperature:'Rücklauf',buffer_temperature:'Puffer',dhw_temperature:'Warmwasser'};
const $=id=>document.getElementById(id); let payload=null;
const fmt=(v,u='',digits=1)=>v==null?'–':`${Number(v).toLocaleString('de-DE',{maximumFractionDigits:digits,minimumFractionDigits:digits})}${u?' '+u:''}`;
const date=v=>v?new Date(v).toLocaleString('de-AT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'–';
function latest(name){return payload.latest.find(x=>x.name===name)?.value ?? null}
function first(...names){for(const name of names){const value=latest(name);if(value!=null)return value}return null}
function status(){return Number(latest('operating_status')||0)}
function setText(id,value){$(id).textContent=value}
function chip(label,active,warn=false){const e=document.createElement('span');e.className=`chip ${active?(warn?'warn':'active'):''}`;e.textContent=label;return e}

function renderCards(){
  const flow=first('flow_temperature','heat_pump_flow_temperature','heat_pump_flow_temperature_1'),ret=latest('return_temperature');
  setText('outside',fmt(latest('outside_temperature'),'°C'));
  setText('room',fmt(first('room_temperature_hc1','actual_temperature_hc1'),'°C'));
  setText('flow',fmt(flow,'°C')); setText('delta',`Differenz ${flow!=null&&ret!=null?fmt(flow-ret,'K'):'–'}`);
  setText('dhw',fmt(latest('dhw_temperature'),'°C')); setText('dhw-set',`Soll ${fmt(latest('dhw_set_temperature'),'°C')}`);
  const s=status(), chips=$('status-chips'); chips.replaceChildren();
  [['Verdichter',6],['Heizen',4],['Warmwasser',5],['HK-Pumpe',0],['Heizstab',3],['Sommer',7],['Abtauen',9]].forEach(([n,b])=>chips.append(chip(n,Boolean(s&(1<<b)),n==='Heizstab')));
  const today=new Date().toISOString().slice(0,10), d=payload.daily.find(x=>x.day===today);
  setText('starts-today',d?.starts??0); setText('average-runtime',d?.average_minutes!=null?`${d.average_minutes} min`:'–');
  const heat=(latest('heat_energy_heating_day')||0)+(latest('heat_energy_dhw_day')||0),power=(latest('electric_energy_heating_day')||0)+(latest('electric_energy_dhw_day')||0);
  setText('cop',power>0?(heat/power).toFixed(2):'–');
}

function setupCanvas(canvas){const rect=canvas.getBoundingClientRect(),dpr=devicePixelRatio||1;canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;const c=canvas.getContext('2d');c.scale(dpr,dpr);return {c,w:rect.width,h:rect.height}}
function lineChart(){
  const selected=Object.keys(COLORS), rows=payload.series.filter(x=>selected.includes(x.name)); $('temp-empty').style.display=rows.length?'none':'grid'; if(!rows.length)return;
  const canvas=$('temperature-chart'),{c,w,h}=setupCanvas(canvas),pad={l:42,r:15,t:12,b:28}; const times=rows.map(x=>Date.parse(x.timestamp_utc)),vals=rows.map(x=>x.value); let minX=Math.min(...times),maxX=Math.max(...times);if(minX===maxX)maxX+=1;
  let minY=Math.floor(Math.min(...vals)-2),maxY=Math.ceil(Math.max(...vals)+2); const x=v=>pad.l+(v-minX)/(maxX-minX)*(w-pad.l-pad.r),y=v=>h-pad.b-(v-minY)/(maxY-minY)*(h-pad.t-pad.b);
  c.font='11px system-ui';c.lineWidth=1;c.strokeStyle='#2a3233';c.fillStyle='#7f8986';c.textAlign='right';for(let i=0;i<5;i++){let v=minY+(maxY-minY)*i/4,py=y(v);c.beginPath();c.moveTo(pad.l,py);c.lineTo(w-pad.r,py);c.stroke();c.fillText(`${v.toFixed(0)}°`,pad.l-8,py+4)}
  c.textAlign='center';for(let i=0;i<4;i++){let t=minX+(maxX-minX)*i/3,px=x(t);c.fillText(new Date(t).toLocaleTimeString('de-AT',{hour:'2-digit',minute:'2-digit'}),px,h-7)}
  for(const name of selected){const points=rows.filter(r=>r.name===name);if(!points.length)continue;c.strokeStyle=COLORS[name];c.lineWidth=2;c.beginPath();points.forEach((p,i)=>{const px=x(Date.parse(p.timestamp_utc)),py=y(p.value);i?c.lineTo(px,py):c.moveTo(px,py)});c.stroke()}
  const legend=$('temp-legend');legend.replaceChildren();selected.filter(n=>rows.some(r=>r.name===n)).forEach(n=>{const s=document.createElement('span');s.innerHTML=`<i style="background:${COLORS[n]}"></i>${LABELS[n]}`;legend.append(s)});
}
function barChart(){
  const rows=payload.daily,canvas=$('starts-chart');$('starts-empty').style.display=rows.length?'none':'grid';if(!rows.length)return;const {c,w,h}=setupCanvas(canvas),pad={l:25,r:8,t:12,b:30},max=Math.max(1,...rows.map(x=>x.starts)),bw=(w-pad.l-pad.r)/rows.length;
  c.font='11px system-ui';rows.forEach((r,i)=>{const bh=(h-pad.t-pad.b)*r.starts/max,x=pad.l+i*bw+bw*.15,y=h-pad.b-bh;c.fillStyle='#a7e22e';c.fillRect(x,y,bw*.7,bh);c.fillStyle='#7f8986';c.textAlign='center';if(rows.length<=10||i%Math.ceil(rows.length/8)===0)c.fillText(r.day.slice(5),x+bw*.35,h-8);if(r.starts)c.fillText(r.starts,x+bw*.35,y-5)});
}
function renderEnergy(){const box=$('energy-cards');box.replaceChildren();[['Wärme Heizen','heat_energy_heating_day'],['Wärme Warmwasser','heat_energy_dhw_day'],['Strom Heizen','electric_energy_heating_day'],['Strom Warmwasser','electric_energy_dhw_day']].forEach(([label,name])=>{const e=document.createElement('div');e.className='energy-item';e.innerHTML=`<span>${label}</span><strong>${fmt(latest(name),'kWh')}</strong>`;box.append(e)})}
function renderRuns(){const body=$('runs');body.replaceChildren();payload.runs.forEach(r=>{const tr=document.createElement('tr'),mode=r.dhw?'Warmwasser':r.heating?'Heizen':'Sonstiges',duration=r.duration_seconds!=null?`${Math.round(r.duration_seconds/60)} min`:'–';tr.innerHTML=`<td>${date(r.started_utc)}${r.complete?'':' *'}</td><td>${mode}</td><td>${duration}</td>`;body.append(tr)});if(!payload.runs.length){const tr=document.createElement('tr');tr.innerHTML='<td colspan="3">Noch keine abgeschlossenen Läufe</td>';body.append(tr)}}
function renderDetails(){const box=$('details');box.replaceChildren();[['Rücklauf',['return_temperature'],'°C'],['Puffer',['buffer_temperature'],'°C'],['Puffer Soll',['buffer_set_temperature'],'°C'],['Volumenstrom',['flow_rate','heat_pump_flow_rate'],'l/min'],['Heizungsdruck',['heating_pressure'],'bar'],['Verdichter Heizen',['compressor_heating_hours','compressor_heating_hours_hp1'],'h'],['Verdichter Warmwasser',['compressor_dhw_hours','compressor_dhw_hours_hp1'],'h']].forEach(([label,names,unit])=>{const d=document.createElement('div');d.innerHTML=`<dt>${label}</dt><dd>${fmt(first(...names),unit,unit==='bar'?2:1)}</dd>`;box.append(d)})}
function renderConnection(){const e=$('connection'),ok=payload.monitor.connected;e.className=`connection ${ok?'online':'offline'}`;e.querySelector('span').textContent=ok?'ISG verbunden':payload.monitor.polling?'Messung läuft':'ISG nicht erreichbar';setText('updated',payload.monitor.last_success?`Letzte Messung ${date(payload.monitor.last_success)}`:'Noch keine erfolgreiche Messung')}
function render(){renderConnection();renderCards();lineChart();barChart();renderEnergy();renderRuns();renderDetails()}
async function load(){try{const r=await fetch(`/api/dashboard?hours=${$('range').value}`,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);payload=await r.json();render()}catch(e){const c=$('connection');c.className='connection offline';c.querySelector('span').textContent='Dashboard offline';console.error(e)}}
$('range').addEventListener('change',load);window.addEventListener('resize',()=>payload&&(lineChart(),barChart()));load();setInterval(load,30000);
