/* Shelly Schedule Manager Dutch card v0.7.0. Shares schedule behavior with the English card. */
import {ShellyScheduleCard} from './shelly-schedule-card.js';

class ShellyScheduleCardNL extends ShellyScheduleCard {
  static get cardType() { return 'shelly-schedule-card-nl'; }

  get _strings() {
    return {
      useType: 'Gebruik type: custom:{type}',
      managementConfig: 'management moet een boolean zijn: true of false',
      completed: '{operation} voltooid.',
      failed: '{operation} mislukt: {error}. Controleer de verbinding met het apparaat en de Home Assistant-meldingen.',
      noDevices: 'Geen Shelly Schedule Manager-apparaten gevonden. Voeg een apparaat toe via Instellingen → Apparaten & diensten en vernieuw het dashboard.',
      title: 'Shelly-schema’s', chooseDevice: 'Kies een Shelly-apparaat',
      working: 'Bezig…', loadButton: '↧ Laden van Shelly', reviewButton: '↥ Controleren en opslaan',
      loadConfirm: 'Laden verwijdert niet-opgeslagen wijzigingen voor dit apparaat. Doorgaan?',
      load: 'Laden', backup: 'Back-up maken', restore: 'Herstel voorbereiden', save: 'Opslaan',
      backupButton: '▣ Back-up maken', restoreButton: '↶ Herstel voorbereiden',
      backupConfirm: 'De opgeslagen back-up voor dit apparaat vervangen door de huidige schema’s op Shelly? Hiervoor worden de schema’s van Shelly gelezen.',
      restoreConfirm: 'De opgeslagen back-up in de schema-editor laden? Alle niet-opgeslagen wijzigingen worden vervangen. Er wordt pas naar Shelly geschreven na controleren en opslaan.',
      reviewLabel: 'Schemawijzigingen controleren', confirmOne: 'Bevestig {count} schemawijziging', confirmMany: 'Bevestig {count} schemawijzigingen',
      timeChange: 'tijd {before} → {after}', daysChange: 'weekdagen {before} → {after}',
      enabled: 'ingeschakeld', disabled: 'uitgeschakeld', modified: 'Schema gewijzigd', job: 'Schema {id}',
      saveWarning: 'Wijzigingen worden alleen naar de geselecteerde Shelly gestuurd. Bestaande RPC-acties blijven behouden. Bij het opslaan van meerdere schema’s kunnen sommige al zijn opgeslagen als een ander mislukt.',
      cancel: 'Annuleren', confirmSave: 'Opslaan naar Shelly bevestigen', dismiss: 'Melding sluiten',
      missingButtons: 'De knoppen voor laden of opslaan zijn niet gevonden voor dit apparaat. Controleer Instellingen → Apparaten & diensten → Shelly Schedule Manager → apparaat → Entiteiten en schakel beide knoppen in.',
      scheduleAction: 'Schema / Actie', time: 'Tijd', enabledHeading: 'Ingeschakeld',
      unknownAction: 'Onbekende actie', customAction: 'Aangepaste actie', switchAction: 'Schakelaar {id} {state}', on: 'AAN', off: 'UIT',
      nameLabel: 'Naam voor schema {id}', renameTitle: 'Schema {id} hernoemen (lokaal opgeslagen in Home Assistant)', rename: 'Schema {id} hernoemen',
      unsaved: ' · Niet-opgeslagen schema', timeLabel: 'Tijd voor schema {id}', timeUpdate: 'Tijd van schema {id} lokaal wijzigen',
      enableLabel: 'Schema {id} inschakelen', enabledUpdate: 'Inschakeling van schema {id} lokaal wijzigen',
      repeat: 'Herhalen', weekdays: ['Zo', 'Ma', 'Di', 'Wo', 'Do', 'Vr', 'Za'],
      advanced: 'Geavanceerde weekdagregel: bewerk op Shelly (blijft behouden bij opslaan)',
      dayLabel: '{day} schema {id}', toggleDay: '{day} wijzigen', requiredDay: 'Selecteer ten minste één weekdag.', daysUpdate: 'Weekdagen van schema {id} lokaal wijzigen',
      noSchedules: 'Geen schema’s gevonden op dit apparaat. Druk op Laden van Shelly.',
      pending: '{count} schema(’s) met niet-opgeslagen wijzigingen. Druk op Controleren en opslaan om ze naar Shelly te schrijven.',
    };
  }
}

if (!customElements.get('shelly-schedule-card-nl')) customElements.define('shelly-schedule-card-nl', ShellyScheduleCardNL);
window.customCards = window.customCards || [];
if (!window.customCards.some(c=>c.type==='shelly-schedule-card-nl')) window.customCards.push({type:'shelly-schedule-card-nl',name:'Shelly Schedule Manager (Nederlands)',description:'Beheer schema’s op meerdere Shelly-apparaten met handmatig laden en opslaan en meldingen in de kaart.'});
