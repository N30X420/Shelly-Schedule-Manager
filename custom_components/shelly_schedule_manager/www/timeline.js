/* Pure event projection: device-local weekly wall times, never inferred relay state. */
export function timelineEvents(jobs, showDisabled = true) {
  const events = [], fallback = [];
  const aliases = {SUN:0, MON:1, TUE:2, WED:3, THU:4, FRI:5, SAT:6};
  for (const job of jobs) {
    if (job.deleted || (!showDisabled && !job.enable)) continue;
    const fields = job.timespec.trim().split(/\s+/);
    const call = job.calls?.length === 1 ? job.calls[0] : null;
    const fixed = fields.length === 6 && fields.slice(0,3).every(x=>/^\d+$/.test(x))
      && Number(fields[0]) < 60 && Number(fields[1]) < 60 && Number(fields[2]) < 24
      && fields[3] === '*' && fields[4] === '*';
    const simple = call?.method?.toLowerCase() === 'switch.set' && Number.isInteger(call.params?.id)
      && typeof call.params?.on === 'boolean' && Object.keys(call.params).every(k=>['id','on'].includes(k));
    const days = fields[5] === '*' ? [0,1,2,3,4,5,6] : (fields[5] || '').toUpperCase().split(',').map(x=>
      Object.hasOwn(aliases,x) ? aliases[x] : /^[0-7]$/.test(x) ? Number(x)%7 : null);
    if (!fixed || !simple || days.some(x=>x===null)) { fallback.push(job); continue; }
    for (const day of new Set(days)) events.push({id:job.id, day, channel:call.params.id,
      seconds:Number(fields[2])*3600+Number(fields[1])*60+Number(fields[0]),
      time:`${fields[2].padStart(2,'0')}:${fields[1].padStart(2,'0')}:${fields[0].padStart(2,'0')}`,
      on:call.params.on, enabled:job.enable, name:job.name, timespec:job.timespec});
  }
  return {events:events.sort((a,b)=>a.day-b.day || a.channel-b.channel || a.seconds-b.seconds), fallback};
}

export function renderTimeline(card, container, device, edit, tr) {
  const el = card._el.bind(card);
  card._timelineView ||= 'week';
  card._timelineDay ??= 1;
  card._timelineDisabled ??= true;
  const days = tr(['Sun','Mon','Tue','Wed','Thu','Fri','Sat'], ['Zo','Ma','Di','Wo','Do','Vr','Za']);
  const controls = el('div',{className:'actions'});
  const view = el('select',{'aria-label':tr('Timeline view','Tijdlijnweergave'), onchange:ev=>{card._timelineView=ev.target.value;card._render();}});
  for (const [value,label] of [['week',tr('Week','Week')],['day',tr('Day','Dag')]]) view.append(el('option',{value,text:label}));
  view.value=card._timelineView;
  const day = el('select',{'aria-label':tr('Select day','Kies een dag'),onchange:ev=>{card._timelineDay=Number(ev.target.value);card._render();}});
  for (const n of [1,2,3,4,5,6,0]) day.append(el('option',{value:String(n),text:days[n]}));
  day.value=String(card._timelineDay);
  const disabled = el('input',{type:'checkbox',checked:card._timelineDisabled,onchange:ev=>{card._timelineDisabled=ev.target.checked;card._render();}});
  controls.append(view,day,el('label',{},disabled,el('span',{text:tr(' Show disabled schedules',' Uitgeschakelde schema’s tonen')})));
  container.append(el('p',{className:'status',text:`${device.title} · ${tr('Device-local time; events only, no inferred active intervals.','Lokale apparaattijd; alleen gebeurtenissen, geen afgeleide actieve intervallen.')}`}),controls);
  const {events,fallback}=timelineEvents(device.jobs,card._timelineDisabled);
  const axis = el('div',{className:'timeline-axis'});
  for (const hour of [0,6,12,18,24]) axis.append(el('span',{text:`${String(hour).padStart(2,'0')}:00`}));
  container.append(axis);
  for (const n of card._timelineView==='week'?[1,2,3,4,5,6,0]:[card._timelineDay]) {
    const group=el('div',{className:'timeline-day'});
    group.append(el('button',{text:days[n],onclick:()=>{card._timelineDay=n;card._timelineView='day';card._render();}}));
    const daily=events.filter(e=>e.day===n);
    for (const channel of [...new Set(daily.map(e=>e.channel))].sort((a,b)=>a-b)) {
      group.append(el('div',{className:'status',text:`${tr('Switch','Schakelaar')} ${channel}`}));
      for(const event of daily.filter(e=>e.channel===channel)) {
        const label=`${event.on?'● '+tr('ON','AAN'):'○ '+tr('OFF','UIT')} · ${event.time} · ${event.name}${event.enabled?'':tr(' (disabled)',' (uitgeschakeld)')}`;
        const details=`${device.title} · ${days[n]} · ${tr('Switch','Schakelaar')} ${channel} · ${label} · ${event.timespec}`;
        const lane=el('div',{className:'timeline-lane'});
        lane.append(el('button',{className:`timeline-event ${event.on?'on':'off'}${event.enabled?'':' disabled-event'}`,
          style:`left:${event.seconds/864}%;`,text:event.on?'●':'○',title:details,'aria-label':details,onclick:()=>edit(event.id)}));
        group.append(lane,el('button',{className:'timeline-caption',text:label,onclick:()=>edit(event.id)}));
      }
    }
    if(!daily.length) group.append(el('span',{className:'status',text:tr('No events','Geen gebeurtenissen')}));
    container.append(group);
  }
  if(fallback.length) {
    container.append(el('p',{className:'status',text:tr('Advanced or custom schedules (exact weekly times unavailable):','Geavanceerde of aangepaste schema’s (geen exacte weektijden beschikbaar):')}));
    for(const job of fallback) container.append(el('button',{text:`${job.name}: ${job.timespec}`,onclick:()=>edit(job.id)}));
  }
}
