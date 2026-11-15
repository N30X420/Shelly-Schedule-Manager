# Shelly Schedule Manager

A custom Home Assistant integration for viewing and editing schedules on Shelly devices. Changes are staged in Home Assistant and written to the device only when you choose **Save to Shelly**.

## Features

- Add multiple Shelly devices through Home Assistant's integration setup.
- Load schedules manually and edit each schedule's time and enabled state.
- Give schedules custom names that are stored locally in Home Assistant.
- Review the schedule action and see which schedules have unsaved changes.
- Save only changed schedules to the device.
- Optionally use the included Lovelace card to manage schedules from a dashboard.
- Read schedules once when the integration starts; no periodic polling of the Shelly device.

## Requirements and limitations

- A Shelly Gen2 or Gen3 device with the RPC Schedule API enabled and reachable from Home Assistant's network.
- The device's local RPC username and password.
- The integration supports schedules with a fixed time in six-field cron format (`second minute hour day month weekday`). The time entity edits only the time; other schedule fields and actions are preserved.
- Schedule actions are displayed but cannot be edited in Home Assistant.
- Custom schedule names are Home Assistant metadata, not Shelly schedule fields. They are saved locally, survive Home Assistant restarts, and are not sent to the device. Names may be up to 80 characters.
- Changing an entity only stages the change locally. It does not update the Shelly until you press **Save to Shelly**.
- **Load from Shelly** replaces the local schedule data and discards any unsaved changes.
- If saving fails partway through, earlier schedules may already have been written. Load the schedules again to inspect the device before retrying.

## Install the integration

1. Copy the `shelly_schedule_manager` folder from this repository into your Home Assistant configuration directory under `custom_components`, so the resulting path is:

   ```text
   <config>/custom_components/shelly_schedule_manager/
   ```

2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **Shelly Schedule Manager**.
4. Enter a device name, its IP address or hostname, and its local RPC username and password. Repeat the setup to add additional devices.
5. The integration reads schedules when it starts. Press **Load from Shelly** on the device page whenever you want to reload them manually.

For each device, the integration creates **Load from Shelly** and **Save to Shelly** buttons. For each schedule it creates a time entity, an enabled switch, and a text entity for its custom name. These entities can be used directly in Home Assistant even if you do not install the optional card. Load and Save results are also reported through Home Assistant notifications.

## Optional Lovelace card

The repository's `shelly-schedule-card.js` is a separate dashboard resource; installing the integration alone does not install the card.

1. Copy `shelly-schedule-card.js` into your Home Assistant `www` directory, creating it if needed:

   ```text
   <config>/www/shelly-schedule-card.js
   ```

2. In **Settings → Dashboards → Resources**, add `/local/shelly-schedule-card.js` as a JavaScript module. If Resources is not available in the UI, enable YAML mode for your dashboard and add:

   ```yaml
   resources:
     - url: /local/shelly-schedule-card.js
       type: module
   ```

3. Add a **Manual** card to a dashboard and use:

   ```yaml
   type: custom:shelly-schedule-card
   title: Shelly schedules
   ```

The card lists configured Shelly Schedule Manager devices. It provides controls to load and save schedules, edit their local name, time, and enabled state, and see pending schedule changes. Names are saved in Home Assistant immediately and are independent of schedule changes. Loading while schedule changes are pending asks for confirmation.

## Security

The integration connects to the device's local RPC endpoint over HTTP and uses HTTP Digest authentication. Use it on a trusted local network and avoid exposing the device's RPC endpoint to the internet.

## API reference

The integration uses Shelly's [Schedule component RPC API](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Schedule/).
