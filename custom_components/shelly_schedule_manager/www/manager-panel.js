import {renderTimeline} from './timeline.js';

const trFor=card=>(english,dutch)=>card.constructor.cardType.endsWith('-nl')?dutch:english;

function switchOutput(job) {
  const call=job.calls?.length===1?job.calls[0]:null;
  const params=call?.params;
  return call?.method?.toLowerCase()==='switch.set' && Number.isInteger(params?.id) && params.id>=0 && typeof params?.on==='boolean'
    ?{switch_id:params.id,on:params.on}:null;
}

export async function openWorkspace(card) {
  if(card._config?.management===false) return;
  card._managerOpen=true;
  if(card._workspaceUnsubscribe || card._workspaceConnecting) {card._render();return;}
  card._workspaceConnecting=true;
  try {
    const unsubscribe=await card._hass.connection.subscribeMessage(data=>{
      if(card._config?.management===false) return;
      card._workspace=data;
      if(card.shadowRoot.activeElement?.tagName!=='INPUT') card._render();
    }, {type:'shelly_schedule_manager/subscribe'});
    if(card._managerDisconnected || card._config?.management===false) unsubscribe(); else card._workspaceUnsubscribe=unsubscribe;
  } catch(error) {
    card._toast(String(error?.message || error),'error');
  } finally {card._workspaceConnecting=false;card._render();}
}

export function closeWorkspace(card) {
  card._managerDisconnected=true;
  if(card._workspaceUnsubscribe) {card._workspaceUnsubscribe();card._workspaceUnsubscribe=null;}
}

async function command(card,action,data={}) {
  if(card._managerBusy || card._config?.management===false) return;
  card._managerBusy=true;card._render();
  try {
    const result=await card._hass.callWS({type:'shelly_schedule_manager/manage',action,data});
    card._managerResult={action,value:result};
    card._workspace=await card._hass.callWS({type:'shelly_schedule_manager/manage',action:'status'});
    if(!['preview','application_preview','history_diff','bulk_preview','bulk_start','diagnostics'].includes(action)) {
      if(action==='test_connection' && result.status!=='connected') card._toast(result.last_error || result.status,'error');
      else card._toast(trFor(card)('Operation completed.','Bewerking voltooid.'));
    }
    return result;
  } catch(error) {card._toast(String(error?.message || error),'error');return null;}
  finally {card._managerBusy=false;card._render();}
}

function download(data,filename) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=filename;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function renderManagerPanel(card,container,chosen) {
  if(card._config?.management===false) return;
  const tr=trFor(card),el=card._el.bind(card);
  const button=(text,onclick,danger=false)=>el('button',{text,disabled:card._managerBusy || card._busy,className:danger?'danger':'',onclick});
  container.append(el('style',{text:`
    .management{margin-top:18px;border-top:2px solid var(--divider-color);padding-top:14px;overflow-wrap:anywhere}
    .management summary{cursor:pointer;font-weight:650;padding:12px 0}.management h3{margin:14px 0 6px}
    .management input:not([type=checkbox]),.management select{max-width:100%;box-sizing:border-box}
    .management label{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:6px 0}
    .management pre{white-space:pre-wrap;font-size:12px;max-height:320px;overflow:auto;background:var(--secondary-background-color);padding:10px}
    .management .danger{color:var(--error-color,#b00020);border:1px solid currentColor}
    .managed-job{border-top:1px solid var(--divider-color);padding:9px 0}
    .timeline-axis{display:flex;justify-content:space-between;font-size:11px;margin-top:10px}
    .timeline-day{border-top:1px solid var(--divider-color);padding:8px 0}.timeline-lane{height:22px;position:relative;margin:4px 15px;background:repeating-linear-gradient(90deg,transparent 0,transparent calc(25% - 1px),var(--divider-color) 25%)}
    button.timeline-event{position:absolute;transform:translateX(-50%);padding:1px 4px;min-width:22px;height:22px;font-size:15px}
    .timeline-event.on{color:var(--success-color,#2e7d32)}.timeline-event.off{color:var(--error-color,#c62828)}
    .timeline-event.disabled-event{opacity:.5;border:1px dashed currentColor}.timeline-caption{font-size:12px;text-align:left;padding:4px}
    .management .actions{margin:6px 0}.manager-editor{border:1px solid var(--primary-color);padding:10px;margin:8px 0}
  `}));
  const box=el('section',{className:'management'});container.append(box);
  box.append(button(tr('Manage schedules / Timeline','Schema’s beheren / Tijdlijn'),()=>{card._managerDisconnected=false;openWorkspace(card);}));
  if(!card._managerOpen) return;
  if(!card._workspace) {box.append(el('p',{text:tr('Loading workspace (administrator account required)…','Werkruimte laden (beheerdersaccount vereist)…')}));return;}
  const workspace=card._workspace;
  const registry=card._hass.devices?.[chosen.id];
  if(card._managerDeviceId!==chosen.id) {
    card._managerDeviceId=chosen.id;
    card._managerEntry=workspace.devices.find(d=>registry?.config_entries?.includes(d.entry_id))?.entry_id || '';
    card._managerResult=null;card._managerEditor=null;
  }
  const selector=el('select',{'aria-label':tr('Managed device','Te beheren apparaat'),onchange:ev=>{card._managerEntry=ev.target.value;card._managerResult=null;card._managerEditor=null;card._render();}});
  selector.append(el('option',{value:'',text:tr('Choose configured device','Kies een geconfigureerd apparaat')}));
  for(const d of workspace.devices) selector.append(el('option',{value:d.entry_id,text:d.title}));
  selector.value=card._managerEntry || '';box.append(selector);
  const device=workspace.devices.find(d=>d.entry_id===card._managerEntry);
  if(!device) return;
  const entry_id=device.entry_id;
  const run=(action,data={})=>command(card,action,{entry_id,...data});
  const show=object=>el('pre',{text:JSON.stringify(object,null,2)});
  const edit=id=>{const job=device.jobs.find(j=>j.id===id);card._managerEditor={id,name:job.name,time:/^\d+ \d+ \d+ /.test(job.timespec)?job.timespec.split(' ').slice(0,3).reverse().map(v=>v.padStart(2,'0')).join(':'):'',weekdays:job.timespec.split(' ')[5] || '',enabled:job.enable,...switchOutput(job)};card._render();};
  box.append(el('h3',{text:device.title}));
  box.append(el('p',{className:'status',text:`${device.jobs.filter(j=>!j.deleted).length}/${device.capabilities.capacity} ${tr('schedule slots','schemaplaatsen')}`}));
  if(device.recovery_required) box.append(el('p',{className:'alert error',text:tr('Uncertain previous write. Load from Shelly before continuing.','Onzekere vorige schrijfactie. Laad van Shelly voordat je doorgaat.')}));
  const actions=el('div',{className:'actions'});
  actions.append(button(tr('Load','Laden'),()=>{if(!device.pending.length || confirm(tr('Discard all local edits?','Alle lokale wijzigingen verwerpen?'))) run('load');}),
    button(tr('Create job','Schema maken'),()=>{card._managerEditor={name:'',time:'08:00:00',weekdays:'0,1,2,3,4,5,6',switch_id:device.capabilities.switches[0] ?? 0,on:true,enabled:true};card._render();}),
    button(tr('Preview & Save all changes','Alle wijzigingen controleren en opslaan'),()=>run('preview')),
    button(tr('Back up device','Back-up maken'),()=>{const description=prompt(tr('Optional snapshot description (max 80 characters)','Optionele beschrijving (maximaal 80 tekens)'),'');if(description!==null)run('backup',{description});}),
    button(tr('Stage latest backup','Laatste back-up klaarzetten'),()=>{if(confirm(tr('Replace unsaved local edits with the latest backup? Nothing is written until Save.','Niet-opgeslagen wijzigingen vervangen door de laatste back-up? Er wordt pas geschreven bij opslaan.')))run('restore',{confirmed:true});}));
  box.append(actions);
  for(const job of device.jobs) {
    const row=el('div',{className:'managed-job'});
    row.append(el('div',{text:`${job.name} · #${job.id} · ${job.timespec} · ${job.enable?tr('enabled','ingeschakeld'):tr('disabled','uitgeschakeld')} · ${job.operation || ''}`}),
      el('div',{className:'status',text:JSON.stringify(job.calls)}));
    if(!job.deleted) row.append(button(tr('Edit','Bewerken'),()=>edit(job.id)),button(tr('Duplicate','Dupliceren'),()=>{const name=prompt(tr('Name for duplicate','Naam voor duplicaat'),job.name);if(name!==null)run('duplicate',{job_id:job.id,name});}),
      button(tr('Delete','Verwijderen'),()=>{if(confirm(`${tr('Stage deletion?','Verwijdering klaarzetten?')}\n${device.title}\n${job.name} (#${job.id})\n${job.timespec}\n${JSON.stringify(job.calls)}`))run('delete',{job_id:job.id,confirmed:true});},true));
    box.append(row);
  }
  if(card._managerEditor) {
    const draft=card._managerEditor;
    const form=el('div',{className:'manager-editor',role:'form','aria-label':tr('Schedule editor','Schema-editor')});
    const input=(key,label,type='text')=>{
      const field=el('input',{type,value:String(draft[key] ?? ''),step:type==='time'?'1':'any',oninput:ev=>{draft[key]=type==='number'?Number(ev.target.value):ev.target.value;}});
      form.append(el('label',{},el('span',{text:label}),field));
    };
    input('name',tr('Name','Naam'));
    input('time',tr('Time (leave blank to preserve advanced rule)','Tijd (laat leeg om geavanceerde regel te behouden)'),'time');
    input('weekdays',tr('Weekdays: 0=Sun … 6=Sat (leave * or advanced unchanged)','Weekdagen: 0=zo … 6=za (laat * of geavanceerd ongewijzigd)'));
    if(draft.id===undefined || draft.switch_id!==undefined) {
      input('switch_id',tr('Target switch ID','Doelschakelaar-ID'),'number');
      form.append(el('label',{},el('input',{type:'checkbox',checked:draft.on,onchange:ev=>{draft.on=ev.target.checked;}}),el('span',{text:tr('ON action (unchecked = OFF)','AAN-actie (uitgevinkt = UIT)')})));
    } else {
      form.append(el('p',{className:'status',text:tr('Custom or multiple RPC actions: edit the output on Shelly.','Aangepaste of meerdere RPC-acties: bewerk de uitgang op Shelly.')}));
    }
    form.append(el('label',{},el('input',{type:'checkbox',checked:draft.enabled,onchange:ev=>{draft.enabled=ev.target.checked;}}),el('span',{text:tr('Enabled','Ingeschakeld')})));
    form.append(button(tr('Stage locally','Lokaal klaarzetten'),async()=>{
      let result;
      if(draft.id===undefined) result=await run('create',{name:draft.name,time:draft.time,weekdays:draft.weekdays,switch_id:draft.switch_id,on:draft.on,enabled:draft.enabled});
      else {
        const current=device.jobs.find(j=>j.id===draft.id),changes={enabled:draft.enabled};
        if(draft.name!==current.name) changes.name=draft.name;
        const output=switchOutput(current);
        if(output) {
          if(draft.switch_id!==output.switch_id) changes.switch_id=draft.switch_id;
          if(draft.on!==output.on) changes.on=draft.on;
        }
        if(draft.time) changes.time=draft.time;
        if(draft.weekdays!==(current.timespec.split(' ')[5] || '')) changes.weekdays=draft.weekdays;
        result=await run('edit',{job_id:draft.id,changes});
      }
      if(result!==null) {card._managerEditor=null;card._render();}
    }),button(tr('Cancel','Annuleren'),()=>{card._managerEditor=null;card._render();}));box.append(form);
  }
  const timeline=el('details',{className:'timeline-section'});
  timeline.open=!!card._timelineOpen;
  timeline.addEventListener('toggle',()=>{card._timelineOpen=timeline.open;});
  timeline.append(el('summary',{text:tr('Weekly timeline','Wekelijkse tijdlijn')}));
  renderTimeline(card,timeline,device,edit,tr);
  box.append(timeline);

  const templates=el('details');
  // Boolean details.open is set explicitly; preserve expanded sections across pushes.
  templates.open=!!card._templatesOpen;templates.addEventListener('toggle',()=>{card._templatesOpen=templates.open;});
  templates.append(el('summary',{text:tr('Templates and copying','Sjablonen en kopiëren')}));
  const templateSelect=el('select',{'aria-label':tr('Template','Sjabloon'),onchange:ev=>{card._templateId=ev.target.value;}});
  templateSelect.append(el('option',{value:'',text:tr('Choose template','Kies een sjabloon')}));
  for(const item of workspace.templates) templateSelect.append(el('option',{value:item.id,text:`${item.name} (${item.jobs.length})`}));
  templateSelect.value=card._templateId || '';templates.append(templateSelect);
  const chooseJob=()=>{const value=prompt(tr('Job ID, or leave blank for entire device','Schema-ID, of laat leeg voor het hele apparaat'),'');return value===null?null:value.trim()===''?{}:{job_id:Number(value)};};
  const mapping=()=>{const value=prompt(tr('Channel mapping as JSON, e.g. {"0":1}; {} keeps channels','Kanaaltoewijzing als JSON, bijv. {"0":1}; {} behoudt kanalen'),'{}');if(value===null)return null;try{return JSON.parse(value);}catch{card._toast(tr('Invalid mapping JSON','Ongeldige JSON-toewijzing'),'error');return null;}};
  templates.append(button(tr('Save as Template','Opslaan als sjabloon'),()=>{const name=prompt(tr('Template name','Sjabloonnaam'));if(name===null)return;const selection=chooseJob();if(selection)run('template_save',{name,...selection});}),
    button(tr('Apply Template (preview)','Sjabloon toepassen (voorbeeld)'),()=>{const map=mapping();if(map)run('application_preview',{source:'template',template_id:card._templateId || '',mapping:map});}),
    button(tr('Rename Template','Sjabloon hernoemen'),()=>{const name=prompt(tr('New template name','Nieuwe sjabloonnaam'));if(name!==null)command(card,'template_rename',{template_id:card._templateId || '',name});}),
    button(tr('Delete Template','Sjabloon verwijderen'),()=>{if(confirm(tr('Delete selected template?','Geselecteerd sjabloon verwijderen?')))command(card,'template_delete',{template_id:card._templateId || '',confirmed:true});},true));
  const target=el('select',{'aria-label':tr('Copy target','Kopieerdoel'),onchange:ev=>{card._copyTarget=ev.target.value;}});
  target.append(el('option',{value:'',text:tr('Copy to device…','Kopiëren naar apparaat…')}));
  for(const item of workspace.devices.filter(d=>d.entry_id!==entry_id)) target.append(el('option',{value:item.entry_id,text:item.title}));
  target.value=card._copyTarget || '';templates.append(target,button(tr('Copy to Device (preview)','Kopiëren naar apparaat (voorbeeld)'),()=>{
    const selection=chooseJob();if(!selection)return;const map=mapping();if(map)command(card,'application_preview',{entry_id:card._copyTarget || '',source:'clone',source_entry_id:entry_id,...selection,mapping:map});
  }));box.append(templates);

  const history=el('details');history.open=!!card._historyOpen;history.addEventListener('toggle',()=>{card._historyOpen=history.open;});
  history.append(el('summary',{text:tr('History and rollback','Geschiedenis en terugzetten')}));
  const snapshots=workspace.history[entry_id] || [];
  const compare=el('select',{'aria-label':tr('Compare with','Vergelijken met'),onchange:ev=>{card._compareId=ev.target.value;}});
  compare.append(el('option',{value:'',text:tr('Compare with current editor','Vergelijken met huidige editor')}));
  for(const snapshot of snapshots) compare.append(el('option',{value:snapshot.id,text:snapshot.timestamp}));
  compare.value=card._compareId || '';history.append(compare);
  history.append(button(tr('Set retention limit','Bewaarlimiet instellen'),()=>{const value=prompt(tr('Snapshots to keep (1–1000)','Aantal te bewaren momentopnamen (1–1000)'),'20');if(value!==null)run('retention',{limit:Number(value)});}));
  for(const snapshot of snapshots) history.append(el('div',{className:'managed-job'},
    el('div',{text:`${snapshot.timestamp} · ${snapshot.source} · ${snapshot.jobs.length} ${tr('jobs','schema’s')} · ${snapshot.diff.length} ${tr('changes','wijzigingen')} · ${snapshot.description || ''}`}),
    button(tr('Compare','Vergelijken'),()=>run('history_diff',{snapshot_id:snapshot.id,...(card._compareId?{other_id:card._compareId}:{})})),
    button(tr('Restore (preview)','Herstellen (voorbeeld)'),()=>run('application_preview',{source:'history',snapshot_id:snapshot.id})),
    button(tr('Delete snapshot','Momentopname verwijderen'),()=>{if(confirm(tr('Delete snapshot permanently?','Momentopname definitief verwijderen?')))run('history_delete',{snapshot_id:snapshot.id,confirmed:true});},true)));
  box.append(history);

  const diagnostics=el('details');diagnostics.open=!!card._diagnosticsOpen;diagnostics.addEventListener('toggle',()=>{card._diagnosticsOpen=diagnostics.open;});
  diagnostics.append(el('summary',{text:tr('Diagnostics','Diagnostiek')}),el('p',{className:'status',text:tr('Manual test results describe the last check, not current availability.','Handmatige testresultaten beschrijven de laatste controle, niet de huidige bereikbaarheid.')}),show(device.diagnostics),
    button(tr('Test Connection','Verbinding testen'),()=>run('test_connection')),
    button(tr('Download Diagnostics','Diagnostiek downloaden'),async()=>{const result=await run('diagnostics');if(result)download(result,'shelly-diagnostics.json');}));box.append(diagnostics);

  const bulk=el('details');bulk.open=!!card._bulkOpen;bulk.addEventListener('toggle',()=>{card._bulkOpen=bulk.open;});bulk.append(el('summary',{text:tr('Bulk Management','Meerdere apparaten beheren')}));
  card._bulkEntries ||= new Set();
  bulk.append(button(tr('Select All','Alles selecteren'),()=>{card._bulkEntries=new Set(workspace.devices.map(d=>d.entry_id));card._render();}));
  for(const item of workspace.devices) bulk.append(el('label',{},el('input',{type:'checkbox',checked:card._bulkEntries.has(item.entry_id),onchange:ev=>{if(ev.target.checked)card._bulkEntries.add(item.entry_id);else card._bulkEntries.delete(item.entry_id);}}),el('span',{text:item.title})));
  const operation=el('select',{'aria-label':tr('Bulk operation','Bulkbewerking'),onchange:ev=>{card._bulkOperation=ev.target.value;}});
  for(const [value,label] of [['template',tr('Apply selected template','Geselecteerd sjabloon toepassen')],['clone',tr('Clone from current device','Klonen van huidig apparaat')],['enable',tr('Enable matching schedules','Overeenkomende schema’s inschakelen')],['disable',tr('Disable matching schedules','Overeenkomende schema’s uitschakelen')]])operation.append(el('option',{value,text:label}));
  operation.value=card._bulkOperation || 'template';bulk.append(operation);
  bulk.append(button(tr('Preview Changes','Wijzigingen bekijken'),()=>{
    const operation=card._bulkOperation || 'template',data={entry_ids:[...card._bulkEntries],operation:operation==='clone'?'template':operation};
    if(operation==='template')data.template_id=card._templateId || '';
    if(operation==='clone'){const selection=chooseJob();if(!selection)return;Object.assign(data,selection,{source_entry_id:entry_id});}
    if(['template','clone'].includes(operation)){const map=mapping();if(!map)return;data.mapping=map;}
    else {const match=prompt(tr('Exact schedule name to match, or blank for ALL','Exacte schemanaam, of leeg voor ALLE schema’s'),'');if(match===null)return;data.match=match;}
    command(card,'bulk_preview',data);
  }));
  for(const batch of workspace.batches) {
    bulk.append(show(batch));
    if(batch.status==='preview')bulk.append(button(tr('Apply to Selected (confirmed writes)','Toepassen op selectie (schrijven bevestigen)'),()=>{
      if(confirm(tr('Write this preview to the selected devices? Operations are not atomic; partial completion is possible.','Dit voorbeeld naar de geselecteerde apparaten schrijven? Bewerkingen zijn niet atomair; gedeeltelijke voltooiing is mogelijk.')))command(card,'bulk_start',{batch_id:batch.id,confirmed:true});
    },true));
  }
  box.append(bulk);
  const result=card._managerResult;
  if(result && ['preview','application_preview','history_diff','bulk_preview'].includes(result.action)) {
    const pane=el('div',{className:'review'},el('h3',{text:tr('Review proposed changes','Voorgestelde wijzigingen controleren')}),show(result.value));
    if(result.action==='preview')pane.append(button(tr('Confirm Save to Shelly','Opslaan naar Shelly bevestigen'),()=>{
      if(confirm(tr('Save all displayed changes to this device?','Alle getoonde wijzigingen naar dit apparaat opslaan?')))run('save',{review_id:result.value.review_id,confirmed:true});
    }));
    if(result.action==='application_preview')pane.append(button(tr('Stage proposal locally','Voorstel lokaal klaarzetten'),()=>{
      if(confirm(tr('Stage this proposal? A restore replaces unsaved local edits. Save remains a separate step.','Dit voorstel klaarzetten? Herstellen vervangt niet-opgeslagen lokale wijzigingen. Opslaan blijft een aparte stap.')))command(card,'application_stage',{application_id:result.value.application_id,confirmed:true});
    }));
    box.append(pane);
  }
}
