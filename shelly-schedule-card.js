/* Shelly Schedule Manager dashboard card v0.3.1. No external libraries or polling. */
class ShellyScheduleCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this._selected = '';
    this._busy = false;
    this._notice = null;
    this._lastSignature = '';
  }

  setConfig(config) {
    if (!config || config.type !== 'custom:shelly-schedule-card') {
      throw new Error('Use type: custom:shelly-schedule-card');
    }
    this._config = config;
    this._selected = config.device_id || '';
    this._lastSignature = '';
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const devices = this._getDevices();
    const summary = JSON.stringify(devices.map(d => [d.id, d.name, d.items.map(i => [i.entity_id, i.state, i.attributes?.unsaved_changes, i.attributes?.action]) ]));
    if (!this._busy && summary !== this._lastSignature) {
      // Preserve an in-progress time edit when unrelated HA state updates arrive.
      if (this.shadowRoot.activeElement?.tagName === 'INPUT') return;
      this._lastSignature = summary;
      this._render();
    }
  }

  getCardSize() { return 8; }
  getGridOptions() { return {columns: 12, min_rows: 5}; }

  _getDevices() {
    if (!this._hass) return [];
    const registry = this._hass.entities || {};
    const groups = new Map();
    for (const [id, info] of Object.entries(registry)) {
      if (info.platform !== 'shelly_schedule_manager' || !info.device_id || !this._hass.states[id]) continue;
      const dev = this._hass.devices?.[info.device_id];
      if (!groups.has(info.device_id)) groups.set(info.device_id, {id: info.device_id, name: dev?.name_by_user || dev?.name || 'Shelly', items: []});
      groups.get(info.device_id).items.push({entity_id:id, state:this._hass.states[id].state, attributes:this._hass.states[id].attributes, unique_id: info.unique_id || '', original_name:info.original_name || '', friendly_name:this._hass.states[id].attributes?.friendly_name || ''});
    }
    return [...groups.values()].filter(d => d.items.some(i => i.entity_id.startsWith('button.'))).sort((a,b)=>a.name.localeCompare(b.name));
  }

  _identify(device) {
    // Home Assistant frontend entity registry entries don't always expose
    // unique_id or original_name. Use entity_id and state friendly_name as
    // fallbacks. Every candidate belongs to this integration's device.
    const rows = new Map();
    let load, save;
    for (const ent of device.items) {
      const uid = String(ent.unique_id || '').toLowerCase();
      const entityId = String(ent.entity_id || '').toLowerCase();
      const name = `${ent.original_name || ''} ${ent.friendly_name || ''}`.toLowerCase();
      if (entityId.startsWith('button.')) {
        if (uid.endsWith('_load') || /(?:^|_)load_from_shelly(?:$|_)/.test(entityId) || /load from shelly/.test(name)) load = ent;
        if (uid.endsWith('_save') || /(?:^|_)save_to_shelly(?:$|_)/.test(entityId) || /save to shelly/.test(name)) save = ent;
      }
      const match = uid.match(/_job_(\d+)_(time|enabled)$/)
        || entityId.match(/_job_(\d+)_(time|enabled)(?:_\d+)?$/)
        || name.match(/job\s+(\d+)\s+(time|enabled)/);
      if (match) {
        const n = Number(match[1]);
        if (!rows.has(n)) rows.set(n, {id:n});
        rows.get(n)[match[2].toLowerCase()] = ent;
      }
    }
    return {load, save, rows:[...rows.values()].sort((a,b)=>a.id-b.id)};
  }

  _el(tag, props = {}, ...children) {
    const e = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (key === 'className') e.className = value;
      else if (key === 'text') e.textContent = value;
      else if (key === 'disabled') e.disabled = !!value;
      else if (key === 'checked') e.checked = !!value;
      else if (key === 'value') e.value = value;
      else if (key.startsWith('on')) e.addEventListener(key.slice(2).toLowerCase(), value);
      else e.setAttribute(key, value);
    }
    for (const child of children) if (child) e.append(child);
    return e;
  }

  _toast(message, kind='success') {
    this._notice = {message,kind};
    clearTimeout(this._noticeTimer);
    this._noticeTimer = setTimeout(() => { this._notice = null; this._render(); }, kind === 'error' ? 15000 : 6000);
    this._render();
  }

  async _call(domain, service, data, operation) {
    if (this._busy) return;
    this._busy = true;
    this._render();
    try {
      await this._hass.callService(domain, service, data);
      this._toast(`${operation} succeeded.`, 'success');
    } catch (error) {
      this._toast(`${operation} failed: ${error?.message || String(error)}. Check the device connection and Home Assistant notifications.`, 'error');
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const root = this.shadowRoot;
    root.replaceChildren();
    const css = this._el('style', {text: `
      :host{display:block;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,Arial,sans-serif)}
      ha-card{display:block;padding:18px 18px 16px;background:var(--ha-card-background,var(--card-background-color));border-radius:var(--ha-card-border-radius,12px);box-shadow:var(--ha-card-box-shadow,none)}
      .header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px;flex-wrap:wrap}
      .heading{font-size:19px;font-weight:650}.hint{font-size:12px;color:var(--secondary-text-color);margin-top:4px}
      select,input[type=time]{background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color,#8886);border-radius:8px;padding:9px;min-width:0;font:inherit}
      select{max-width:100%;min-width:150px}.actions{display:flex;gap:9px;flex-wrap:wrap;margin:14px 0}
      button{border:0;border-radius:9px;padding:11px 15px;font:inherit;cursor:pointer;font-weight:600;background:var(--secondary-background-color,#eee);color:var(--primary-text-color)}
      button.primary{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}
      button:disabled,select:disabled,input:disabled{opacity:.55;cursor:not-allowed}
      .row{display:grid;grid-template-columns:minmax(105px,1fr) minmax(110px,150px) 68px;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--divider-color,#ddd)}
      .job{font-weight:600;font-size:14px}.action{font-size:12px;color:var(--secondary-text-color);margin-top:3px}
      .pending{font-size:11px;color:var(--warning-color,#d68b00);font-weight:600;margin-left:6px}
      .switch{width:42px;height:24px;accent-color:var(--primary-color);cursor:pointer;justify-self:center}
      .labels{font-size:11px;color:var(--secondary-text-color);display:grid;grid-template-columns:minmax(105px,1fr) minmax(110px,150px) 68px;gap:12px;margin-bottom:5px}
      .alert{padding:12px;margin:8px 0;border-radius:9px;font-size:13px;line-height:1.45;overflow-wrap:anywhere}
      .alert.success{background:color-mix(in srgb,var(--success-color,#4caf50) 14%,transparent)}
      .alert.error{background:color-mix(in srgb,var(--error-color,#f44336) 15%,transparent)}
      .foot{margin-top:12px;font-size:12px;color:var(--secondary-text-color)}
      @media(max-width:390px){ha-card{padding:13px}.row,.labels{grid-template-columns:minmax(90px,1fr) 105px 48px;gap:6px}input[type=time]{width:100%;box-sizing:border-box;padding:7px}}
    `});
    root.append(css);
    const card = this._el('ha-card'); root.append(card);
    const devices = this._getDevices();
    if (!devices.length) {
      card.append(this._el('div',{className:'heading',text:'Shelly Schedule Manager'}), this._el('p',{text:'No Shelly Schedule Manager devices found. Add a device through Settings → Devices & services, then refresh the dashboard.'}));
      return;
    }
    if (!devices.some(d=>d.id===this._selected)) this._selected=devices[0].id;
    const chosen = devices.find(d=>d.id===this._selected);
    const header = this._el('div',{className:'header'});
    header.append(this._el('div',{},this._el('div',{className:'heading',text:this._config.title || 'Shelly schedules'}),this._el('div',{className:'hint',text:'Edit locally, then Save to Shelly'})));
    const selector = this._el('select',{ 'aria-label':'Choose Shelly device', disabled:this._busy, onchange:(ev)=>{this._selected=ev.target.value;this._notice=null;this._render();}});
    devices.forEach(d => selector.append(this._el('option',{value:d.id,text:d.name})));
    selector.value=this._selected;
    header.append(selector);card.append(header);
    const {load,save,rows}=this._identify(chosen);
    const pending=rows.filter(r=>r.time?.attributes?.unsaved_changes || r.enabled?.attributes?.unsaved_changes).length;
    const actions=this._el('div',{className:'actions'});
    actions.append(this._el('button',{text:this._busy?'Working…':'↧ Load from Shelly',disabled:this._busy || !load || load.state==='unavailable',onclick:()=>{
      if (pending && !confirm('Load will discard unsaved changes for this device. Continue?')) return;
      this._call('button','press',{entity_id:load.entity_id},'Load');
    }}));
    actions.append(this._el('button',{className:'primary',text:this._busy?'Working…':`↥ Save to Shelly${pending?` (${pending})`:''}`,disabled:this._busy || !save || save.state==='unavailable',onclick:()=>this._call('button','press',{entity_id:save.entity_id},'Save')}));
    card.append(actions);
    if (this._notice) {
      const alert = this._el('div',{className:`alert ${this._notice.kind}`,role:'status'},this._el('span',{text:this._notice.message}));
      alert.append(this._el('button',{text:'×', 'aria-label':'Dismiss notification',style:'float:right;padding:0 2px;margin-left:6px',onclick:()=>{clearTimeout(this._noticeTimer);this._notice=null;this._render();}}));
      card.append(alert);
    }
    if (!load || !save) card.append(this._el('div',{className:'alert error',text:'Load/Save button entities not found for this device. Check Settings → Devices & services → Shelly Schedule Manager → device → Entities; ensure both buttons are enabled.'}));
    card.append(this._el('div',{className:'labels'},this._el('span',{text:'Schedule / Action'}),this._el('span',{text:'Time'}),this._el('span',{text:'Enabled'})));
    for (const row of rows) {
      const action=row.time?.attributes?.action || row.enabled?.attributes?.action || 'Unknown action';
      const dirty=!!(row.time?.attributes?.unsaved_changes || row.enabled?.attributes?.unsaved_changes);
      const label=this._el('div',{},this._el('div',{className:'job',text:`Job ${row.id}${dirty?' • Unsaved':''}`}),this._el('div',{className:'action',text:action}));
      const val=row.time?.state || '';
      const valid=/^\d{2}:\d{2}(:\d{2})?$/.test(val);
      const time=this._el('input',{type:'time',step:'1',value:valid?(val.length===5?`${val}:00`:val):'',disabled:this._busy || !row.time || !valid,'aria-label':`Time for job ${row.id}`,onchange:(ev)=>{
        const v=ev.target.value;
        if (v) this._call('time','set_value',{entity_id:row.time.entity_id,time:v.length===5?`${v}:00`:v},`Update job ${row.id} time locally`);
      }});
      const enabled=this._el('input',{type:'checkbox',className:'switch',checked:row.enabled?.state==='on',disabled:this._busy || !row.enabled || !['on','off'].includes(row.enabled.state),'aria-label':`Enable job ${row.id}`,onchange:(ev)=>this._call('switch',ev.target.checked?'turn_on':'turn_off',{entity_id:row.enabled.entity_id},`Update job ${row.id} enabled state locally`)});
      card.append(this._el('div',{className:'row'},label,time,enabled));
    }
    if (!rows.length) card.append(this._el('p',{text:'No schedules found on this device. Press Load from Shelly.'}));
    card.append(this._el('div',{className:'foot',text: pending?`${pending} schedule(s) have unsaved changes. Press Save to write them to the Shelly.`:'No pending changes. The card makes no periodic requests to the Shelly.'}));
  }
}
if (!customElements.get('shelly-schedule-card')) customElements.define('shelly-schedule-card',ShellyScheduleCard);
window.customCards = window.customCards || [];
if (!window.customCards.some(c=>c.type==='shelly-schedule-card')) window.customCards.push({type:'shelly-schedule-card',name:'Shelly Schedule Manager',description:'Manage schedules across multiple Shelly devices with manual Load/Save and inline notifications.'});
