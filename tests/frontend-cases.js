/* Dependency-free DOM stand-in and shared executable browser logic tests. */
export class FakeElement {
  constructor(tag='host') {this.tagName=tag.toUpperCase();this.children=[];this.attrs={};this.events={};this.textContent='';}
  attachShadow() {this.shadowRoot=new FakeElement('shadow');}
  append(...children) {this.children.push(...children);}
  replaceChildren(...children) {this.children=children;}
  setAttribute(key,value) {this.attrs[key]=value;}
  addEventListener(key,value) {this.events[key]=value;}
  click() {return this.events.click?.();}
}

export async function runFrontendTests({timelineEvents,classes}) {
  const passed=[];
  const assert=(value,label)=>{if(!value)throw Error(label);};
  const same=(a,b,label)=>assert(JSON.stringify(a)===JSON.stringify(b),label);
  const job=(id,timespec='0 0 8 * * 1',channel=0,on=true)=>({id,timespec,enable:true,name:`Name ${id}`,calls:[{method:'Switch.Set',params:{id:channel,on}}]});
  const sunday=timelineEvents([job(1,'0 0 8 * * SUN,7'),job(2,'0 0 8 * * MON')]);
  same(sunday.events.map(e=>e.day),[0,1],'Sunday alias, 7 and Monday mapping');
  same(timelineEvents([job(1,'0 0 8 * * *')]).events.length,7,'Daily events');
  const midnight=timelineEvents([job(1,'0 59 23 * * 1'),job(2,'0 1 0 * * 2',0,false)]);
  same(midnight.events.map(e=>[e.day,e.seconds]),[[1,86340],[2,60]],'Midnight events retain actual weekdays');
  assert(midnight.events.every(e=>!('interval' in e)),'No fabricated active intervals');
  const disabled=job(1);disabled.enable=false;
  same(timelineEvents([disabled],false).events.length,0,'Hide disabled jobs');
  same(timelineEvents([disabled],true).events[0].enabled,false,'Disabled state');
  same(timelineEvents([job(1),job(2,undefined,1)]).events.map(e=>e.channel),[0,1],'Separate switch channels');
  const multi=job(1);multi.calls.push({method:'Switch.Set',params:{id:1,on:false}});
  const timer=job(2);timer.calls[0].params.toggle_after=10;
  const fallback=timelineEvents([multi,timer,job(3,'@sunrise'),job(4,'0 0 8 1 * 1'),job(5,'0 0 8 * * MON-FRI')]);
  same(fallback.events.length,0,'Complex schedules have no invented precise times');
  same(fallback.fallback.length,5,'Complex fallback list');
  passed.push('timeline weekdays, midnight, disabled jobs, channels and complex fallback');
  const flatten=node=>[node,...node.children.flatMap(flatten)];
  const text=node=>flatten(node).map(n=>n.textContent).join('\n');
  const [English,Dutch]=classes;
  same(Object.keys(new English()._strings).sort(),Object.keys(new Dutch()._strings).sort(),'Language key parity');
  for(const Card of classes) {
    const dutch=Card===Dutch,card=new Card();
    const inventoryCard=new Card();
    inventoryCard.setConfig({type:`custom:${Card.cardType}`,management:false});
    const loadButton={entity_id:'button.load',unique_id:'entry_load',state:'unknown',attributes:{schedule_job_ids:[2,9,12]}};
    const inventoryItems=[loadButton,...['save','backup','restore'].map(op=>({entity_id:`button.${op}`,unique_id:`entry_${op}`,state:'unknown'}))];
    for(const id of [1,2,3,4,5,6,7,8,9,12]) {
      const configured=[2,9,12].includes(id);
      inventoryItems.push({entity_id:`time.job_${id}_time`,unique_id:`entry_job_${id}_time`,
        state:configured && id!==9?'08:00:00':'unavailable',attributes:{}});
      inventoryItems.push({entity_id:`switch.job_${id}_enabled`,unique_id:`entry_job_${id}_enabled`,
        state:configured?(id===9?'on':'off'):'unavailable',attributes:{}});
    }
    const retainedName={entity_id:'text.job_7_name',unique_id:'entry_job_7_name',state:'Old job name',attributes:{}};
    inventoryItems.push(retainedName);
    const inventoryDevice={id:'inventory',name:'Inventory',items:inventoryItems};
    inventoryCard._getDevices=()=>[inventoryDevice];
    inventoryCard.hass={};
    same(inventoryCard._identify(inventoryDevice).rows.map(r=>r.id),[2,9,12],'Only configured IDs appear, including jobs beyond eight');
    same(flatten(inventoryCard.shadowRoot).filter(e=>e.className==='row').length,3,'No stale or placeholder schedule rows');
    same(flatten(inventoryCard.shadowRoot).find(e=>e.className==='actions').children.length,2,'Main controls contain only Load and Review & Save');
    same(inventoryCard.getCardSize(),10,'Layout estimate follows the configured row count');
    loadButton.attributes.schedule_job_ids=[];
    inventoryCard.hass={};
    same(flatten(inventoryCard.shadowRoot).filter(e=>e.className==='row').length,0,'An empty inventory updates the card without helper-state changes');
    same(inventoryCard.getCardSize(),4,'Empty inventory does not reserve eight jobs of height');
    delete loadButton.attributes.schedule_job_ids;
    retainedName.state='unavailable';
    same(inventoryCard._identify(inventoryDevice).rows.map(r=>r.id),[2,9,12],'Older-backend fallback hides missing jobs but keeps disabled and advanced jobs');
    passed.push(`${dutch?'Dutch':'English'} configured schedule inventory, empty devices, stale helpers and dynamic layout`);
    const notices=[];card._toast=(message,kind)=>notices.push({message,kind});
    card.setConfig({type:`custom:${Card.cardType}`});
    const calls=[];
    const device={entry_id:'entry',title:'Keuken',jobs:[job(1)],pending:[],diagnostics:{status:'not_checked'},capabilities:{switches:[0],capacity:20}};
    const workspace={devices:[device],templates:[],history:{entry:[]},batches:[]};
    card._hass={devices:{device:{config_entries:['entry']}},callWS:async msg=>{calls.push(msg);return msg.action==='status'?workspace:{};}};
    card._getDevices=()=>[{id:'device',name:'Keuken',items:[]}];
    card._managerOpen=true;card._workspace=workspace;
    card._render();
    same(card._config.management,true,'Management stays enabled by default');
    assert(text(card.shadowRoot).includes(dutch?'Wekelijkse tijdlijn':'Weekly timeline'),'Timeline rendered');
    const timelineSection=()=>flatten(card.shadowRoot).find(e=>e.tagName==='DETAILS'&&e.className==='timeline-section');
    assert(timelineSection() && !timelineSection().open,'Timeline starts in a collapsed details container');
    timelineSection().open=true;timelineSection().events.toggle();card._render();
    assert(timelineSection().open,'Expanded timeline persists across renders');
    timelineSection().open=false;timelineSection().events.toggle();card._render();
    assert(!timelineSection().open,'Collapsed timeline persists across renders');
    assert(text(card.shadowRoot).includes(dutch?'Meerdere apparaten beheren':'Bulk Management'),'Bulk controls rendered');
    assert(flatten(card.shadowRoot).some(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Back-up maken':'Back up device')),'Backup remains in the management workspace');
    assert(flatten(card.shadowRoot).some(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Laatste back-up klaarzetten':'Stage latest backup')),'Restore remains in the management workspace');
    assert(!text(card.shadowRoot).includes(dutch?'Bewerk lokaal':'Edit locally'),'Header editing hint is removed');
    assert(!text(card.shadowRoot).includes(dutch?'Namen en back-ups':'Names and backups'),'Storage footer is removed');
    assert(!text(card.shadowRoot).includes(dutch?'gedocumenteerde Shelly-limiet':'Shelly documented limit'),'Capacity note is removed');
    const createButton=flatten(card.shadowRoot).find(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Schema maken':'Create job'));
    createButton.click();
    same(card._managerEditor.weekdays,'0,1,2,3,4,5,6','New schedules default to every day');
    same(calls.length,0,'Opening a new daily schedule makes no backend calls');
    card._managerEditor=null;card._render();
    const editor=flatten(card.shadowRoot).find(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Bewerken':'Edit'));
    editor.click();
    assert(flatten(card.shadowRoot).some(e=>e.attrs.role==='form'),'Event/job editor renders');
    same(card._managerEditor.switch_id,0,'Existing output is loaded into the editor');
    same(card._managerEditor.on,true,'Existing ON/OFF action is loaded into the editor');
    card._managerEditor=null;
    const malicious='<img src=x onerror=alert(1)>';
    device.jobs[0].name=malicious;card._render();
    assert(text(card.shadowRoot).includes(malicious),'User names remain text');
    assert(!flatten(card.shadowRoot).some(e=>e.tagName==='IMG'),'No HTML injection');
    // No command or device write happens just by rendering the workspace.
    same(calls.length,0,'Rendering is local');
    flatten(card.shadowRoot).find(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Bewerken':'Edit')).click();
    const outputForm=flatten(card.shadowRoot).find(e=>e.attrs.role==='form');
    const outputInput=flatten(outputForm).find(e=>e.tagName==='INPUT'&&e.attrs.type==='number');
    outputInput.events.input({target:{value:'1'}});
    const onInput=flatten(outputForm).find(e=>e.tagName==='INPUT'&&e.attrs.type==='checkbox');
    onInput.events.change({target:{checked:false}});
    await flatten(outputForm).find(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Lokaal klaarzetten':'Stage locally')).click();
    const outputEdit=calls.find(call=>call.action==='edit');
    same(outputEdit.data.changes.switch_id,1,'Edit sends the staged output ID');
    same(outputEdit.data.changes.on,false,'Edit sends the staged OFF action');
    same(device.jobs[0].calls[0].params,{id:0,on:true},'Editing does not mutate the original calls in the frontend');
    device.jobs[0].calls.push({method:'Switch.Set',params:{id:1,on:false}});
    card._render();
    flatten(card.shadowRoot).find(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Bewerken':'Edit')).click();
    const customForm=flatten(card.shadowRoot).find(e=>e.attrs.role==='form');
    assert(!flatten(customForm).some(e=>e.tagName==='INPUT'&&e.attrs.type==='number'),'Multi-call schedules do not expose output editing');
    assert(text(customForm).includes(dutch?'bewerk de uitgang op Shelly':'edit the output on Shelly'),'Custom output limitation is explained');
    device.jobs[0].calls.pop();card._managerEditor=null;
    card._managerResult={action:'application_preview',value:{application_id:'proposal',preview:{changes:1}}};card._render();
    assert(text(card.shadowRoot).includes(dutch?'Voorstel lokaal klaarzetten':'Stage proposal locally'),'Application preview requires staging');
    card._managerResult={action:'preview',value:{review_id:'review',changes:[{operation:'create'}]}};card._render();
    assert(text(card.shadowRoot).includes(dutch?'Opslaan naar Shelly bevestigen':'Confirm Save to Shelly'),'Save confirmation exists');
    const confirmSave=flatten(card.shadowRoot).find(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Opslaan naar Shelly bevestigen':'Confirm Save to Shelly'));
    confirmSave.click();
    for(let n=0;n<8;n++)await Promise.resolve();
    const write=calls.find(call=>call.action==='save');
    same(write.data,{entry_id:'entry',review_id:'review',confirmed:true},'Save uses current entry and reviewed proposal');
    card._managerEditor={name:'New',time:'10:30:00',weekdays:'1,2',switch_id:0,on:false,enabled:true};card._render();
    const stage=flatten(card.shadowRoot).find(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Lokaal klaarzetten':'Stage locally'));
    await stage.click();
    const create=calls.find(call=>call.action==='create');
    same(create.data,{entry_id:'entry',name:'New',time:'10:30:00',weekdays:'1,2',switch_id:0,on:false,enabled:true},'Create form stages structured values');
    const managementToggle=()=>flatten(card.shadowRoot).find(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Schema’s beheren / Tijdlijn':'Manage schedules / Timeline'));
    let collapsedUnsubscribe=false,subscriptions=0,reopenedUnsubscribe=false;
    const preservedDraft={id:1,name:'Keep draft',time:'08:00:00',weekdays:'1',enabled:true,switch_id:0,on:true};
    card._managerEditor=preservedDraft;
    card._workspaceUnsubscribe=()=>{collapsedUnsubscribe=true;};card._render();
    same(managementToggle().attrs['aria-expanded'],'true','Open workspace exposes expanded state');
    const callsBeforeToggle=calls.length;
    managementToggle().click();
    assert(!card._managerOpen && collapsedUnsubscribe,'Second click closes and unsubscribes the workspace');
    same(managementToggle().attrs['aria-expanded'],'false','Closed workspace exposes collapsed state');
    assert(!flatten(card.shadowRoot).some(e=>e.attrs.role==='form'),'Closing hides the editor');
    assert(card._managerEditor===preservedDraft,'Closing preserves the editor draft');
    card._hass.connection={subscribeMessage:async callback=>{subscriptions++;callback(workspace);return()=>{reopenedUnsubscribe=true;};}};
    managementToggle().click();for(let n=0;n<8;n++)await Promise.resolve();
    assert(card._managerOpen && card._managerEditor===preservedDraft,'Another click reopens the preserved editor');
    same(subscriptions,1,'Reopening creates exactly one subscription');
    same(calls.length,callsBeforeToggle,'Toggling performs no management commands or device writes');
    const activeUnsubscribe=card._workspaceUnsubscribe;
    let unsubscribed=false;card._workspaceUnsubscribe=()=>{unsubscribed=true;activeUnsubscribe?.();};
    const beforeHide=calls.length;
    card.setConfig({type:`custom:${Card.cardType}`,management:false});
    assert(unsubscribed,'Disabling management unsubscribes the open workspace');
    assert(reopenedUnsubscribe,'Disabling also cleans up the reopened subscription');
    assert(!flatten(card.shadowRoot).some(e=>e.className==='management'),'Disabled management has no button or workspace');
    assert(!card._managerOpen && card._workspace===null && card._managerEditor===null,'Disabling clears visible workspace state');
    confirmSave.click();for(let n=0;n<8;n++)await Promise.resolve();
    same(calls.length,beforeHide,'Stale management controls cannot issue commands after disabling');
    card.setConfig({type:`custom:${Card.cardType}`,management:true});
    assert(flatten(card.shadowRoot).some(e=>e.className==='management'),'Management can be explicitly re-enabled');
    for(const value of ['false','true',0,1,null]) {
      let rejected=false;try{card.setConfig({type:`custom:${Card.cardType}`,management:value});}catch{rejected=true;}
      assert(rejected,`Invalid management value rejected: ${value}`);
    }
    let receive,finish,pendingUnsubscribed=false;
    card._hass.connection={subscribeMessage:callback=>{receive=callback;return new Promise(resolve=>{finish=resolve;});}};
    const openButton=flatten(card.shadowRoot).find(e=>e.tagName==='BUTTON'&&e.textContent===(dutch?'Schema’s beheren / Tijdlijn':'Manage schedules / Timeline'));
    openButton.click();
    card.setConfig({type:`custom:${Card.cardType}`,management:false});
    receive(workspace);
    assert(card._workspace===null,'Late workspace messages are ignored when management is hidden');
    finish(()=>{pendingUnsubscribed=true;});for(let n=0;n<8;n++)await Promise.resolve();
    assert(pendingUnsubscribed && !card._workspaceUnsubscribe,'Pending subscriptions are cleaned up when disabled');
    card.setConfig({type:`custom:${Card.cardType}`,management:true});
    pendingUnsubscribed=false;
    managementToggle().click();
    managementToggle().click();
    assert(!card._managerOpen,'Workspace can close before subscription setup finishes');
    receive(workspace);
    assert(card._workspace===null,'Messages arriving after collapse are ignored');
    finish(()=>{pendingUnsubscribed=true;});for(let n=0;n<8;n++)await Promise.resolve();
    assert(pendingUnsubscribed && !card._workspaceUnsubscribe && !card._managerOpen,'Late subscription completion cannot reopen a collapsed workspace');
    unsubscribed=false;card._workspaceUnsubscribe=()=>{unsubscribed=true;};card.disconnectedCallback();
    assert(unsubscribed,'Workspace unsubscribes when card is removed');
    passed.push(`${dutch?'Dutch':'English'} workspace, editor, previews and safe text rendering`);
    passed.push(`${dutch?'Dutch':'English'} management visibility, subscription cleanup and collapsible timeline`);
    passed.push(`${dutch?'Dutch':'English'} existing output/action editing and custom-action preservation`);
    passed.push(`${dutch?'Dutch':'English'} workspace toggle, preserved drafts and pending-close cleanup`);
  }
  return passed;
}
