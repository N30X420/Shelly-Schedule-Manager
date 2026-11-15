import test from 'node:test';
import {FakeElement,runFrontendTests} from './frontend-cases.js';

globalThis.HTMLElement=FakeElement;
globalThis.document={createElement:tag=>new FakeElement(tag)};
const registry=new Map();
globalThis.customElements={get:key=>registry.get(key),define:(key,value)=>{if(registry.has(key))throw Error('Duplicate card');registry.set(key,value);}};
globalThis.window={customCards:[]};
globalThis.confirm=()=>true;
globalThis.prompt=()=>null;

const {timelineEvents}=await import('../custom_components/shelly_schedule_manager/www/timeline.js');
await import('../custom_components/shelly_schedule_manager/www/shelly-schedule-card-nl.js');

test('English/Dutch cards and all timeline projections',async()=>{
  await runFrontendTests({timelineEvents,classes:[registry.get('shelly-schedule-card'),registry.get('shelly-schedule-card-nl')]});
  if(registry.size!==2 || window.customCards.length!==2)throw Error('Card registration conflict');
});
