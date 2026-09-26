const $=id=>document.getElementById(id);
const categoryLabels={temperature:'Temperatur',climate:'Raumklima',hydraulic:'Hydraulik',status:'Status',energy:'Energie',counter:'Zähler'};
const number=v=>v==null?'–':Number(v).toLocaleString('de-DE',{maximumFractionDigits:2});
let registers=[];
let registerTimestamp=null;
function addCell(row,value){const cell=document.createElement('td');cell.textContent=value;row.append(cell)}
function renderRegisters(){
  const body=$('register-rows'),updated=$('register-updated');
  const showUnavailable=$('show-unavailable').checked;
  const unavailableCount=registers.filter(reg=>reg.raw_value===32768).length;
  const visibleRegisters=showUnavailable?registers:registers.filter(reg=>reg.raw_value!==32768);
  body.replaceChildren();
  visibleRegisters.forEach(reg=>{
    const row=document.createElement('tr');addCell(row,reg.address);addCell(row,reg.name);addCell(row,reg.profile);addCell(row,categoryLabels[reg.category]||reg.category);addCell(row,reg.raw_value==null?'–':reg.raw_value);
    addCell(row,reg.value==null?(reg.raw_value===32768?'Nicht verfügbar':'–'):`${number(reg.value)}${reg.unit?` ${reg.unit}`:''}`);
    addCell(row,reg.error?`Fehler: ${reg.error}`:reg.raw_value===32768?'Nicht verfügbar':'OK');if(reg.error)row.className='register-error';body.append(row);
  });
  if(!visibleRegisters.length){
    const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=7;cell.textContent='Keine Register entsprechen dem Filter.';row.append(cell);body.append(row);
  }
  const status=[`Frisch gelesen ${new Date(registerTimestamp).toLocaleString('de-AT')}`,`${visibleRegisters.length} von ${registers.length} Registern`,`${registers.filter(reg=>reg.error).length} Lesefehler`];
  if(!showUnavailable&&unavailableCount)status.splice(2,0,`${unavailableCount} nicht verfügbar ausgeblendet`);
  updated.textContent=status.join(' · ');
}
async function loadRegisters(){
  const button=$('refresh-registers'),body=$('register-rows'),updated=$('register-updated');button.disabled=true;button.textContent='Lese …';updated.textContent='Frage ISG ab …';
  try{
    const response=await fetch('/api/registers',{cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.error||`HTTP ${response.status}`);
    registers=data.registers;registerTimestamp=data.timestamp_utc;renderRegisters();
  }catch(error){body.replaceChildren();const row=document.createElement('tr');const cell=document.createElement('td');cell.colSpan=7;cell.textContent=`Registerabfrage fehlgeschlagen: ${error.message}`;row.append(cell);body.append(row);updated.textContent='Keine aktuelle Registerantwort'}
  finally{button.disabled=false;button.textContent='Jetzt auslesen'}
}
$('refresh-registers').addEventListener('click',loadRegisters);loadRegisters();
$('show-unavailable').addEventListener('change',renderRegisters);
