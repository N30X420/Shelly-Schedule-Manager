# Shelly Schedule Manager

A custom Home Assistant integration for viewing and editing schedules on Shelly devices. Changes are staged in Home Assistant and written to the device only when you choose **Save to Shelly**.

## Features

- Add multiple Shelly devices through Home Assistant's integration setup.
- Load schedules manually and edit each schedule's time, weekdays, and enabled state.
- Give schedules custom names that are stored locally in Home Assistant.
- Review the schedule action and see which schedules have unsaved changes.
- Review pending changes in the card before confirming a save.
- Save only changed schedules, with checks for external changes before writing and automatic read-back verification afterward.
- Back up device schedules locally and stage a restore for review before saving.
- See operation results in card messages and per-device persistent Home Assistant notifications.
- Optionally use the included Lovelace card to manage schedules from a dashboard.
- Read schedules once when the integration starts; no periodic polling of the Shelly device.

## Requirements and limitations

- A Shelly Gen2 or Gen3 device with the RPC Schedule API enabled and reachable from Home Assistant's network.
- The device's local RPC username and password.
- The integration supports schedules with a fixed time in six-field cron format (`second minute hour day month weekday`). The time entity edits only the time; the weekday entity edits only the weekday field. Day-of-month, month, and schedule actions are preserved.
- Weekday editing supports `*`, individual numeric days, weekday names, and comma-separated lists. Advanced weekday expressions such as ranges or steps are preserved but must be edited on the Shelly. At least one weekday must remain selected.
- Create or delete schedules on the Shelly; this integration edits existing schedules only.
- Schedule actions are displayed but cannot be edited in Home Assistant.
- Custom schedule names are Home Assistant metadata, not Shelly schedule fields. They are saved locally, survive Home Assistant restarts, and are not sent to the device. Names may be up to 80 characters.
- Changing an entity only stages the change locally. It does not update the Shelly until you press **Save to Shelly**.
- **Load from Shelly** replaces the local schedule data and discards any unsaved changes.
- Saving checks the edited schedules against the last successful Load or verified Save. If an edited schedule was removed or its time, weekdays, enabled state, or action changed on the device, nothing is written. Load again, review the device values, and reapply your edits.
- If saving fails partway through, earlier schedules may already have been written. Load the schedules again to inspect the device before retrying.

## Install the integration

### HACS (custom repository)

1. Open **HACS** in Home Assistant, open the three-dot menu, and choose **Custom repositories**.
2. Add `https://github.com/N30X420/Shelly-Schedule-Manager` with type **Integration**.
3. Find **Shelly Schedule Manager** in HACS and download it.
4. Restart Home Assistant, then follow the configuration steps below.

HACS manages the integration files and updates. The optional Lovelace card still needs the separate installation described below. This repository is installed as a custom repository; it is not listed in the default HACS catalog.

### Manual installation

1. Copy `custom_components/shelly_schedule_manager` from this repository into your Home Assistant configuration directory under `custom_components`, so the resulting path is:

   ```text
   <config>/custom_components/shelly_schedule_manager/
   ```

2. Restart Home Assistant.

### Configure a device

1. Go to **Settings → Devices & services → Add integration** and search for **Shelly Schedule Manager**.
2. Enter a device name, its IP address or hostname, and its local RPC username and password. Repeat the setup to add additional devices.
3. The integration reads schedules when it starts. Press **Load from Shelly** on the device page whenever you want to reload them manually.

For each device, the integration creates these buttons:

| Button | Behavior |
| --- | --- |
| **Load from Shelly** | Read current device schedules, replacing local schedule edits. |
| **Save to Shelly** | Check for conflicts, write changed schedules, and verify the result. |
| **Back up Shelly schedules** | Read device schedules and replace the stored backup for this device. |
| **Stage backup restore** | Copy backed-up schedule settings into the local editor for review and saving. |

For each schedule it creates a time entity, an enabled switch, a text entity for its custom name, and a **Job … days** text entity for weekdays. Set weekdays as comma-separated numbers (`0` = Sunday through `6` = Saturday); for example, `1,2,3,4,5` selects Monday through Friday. Advanced weekday rules appear as `advanced` and cannot be changed through this entity.

These entities can be used directly in Home Assistant even if you do not install the optional card. Pressing **Save to Shelly** directly applies staged changes without the card's review screen. Operation results, including authentication, connection, conflict, and verification errors, appear in a persistent Home Assistant notification for the device.

## Optional Lovelace card

The repository's `shelly-schedule-card.js` is a separate dashboard resource. HACS installs only `custom_components/shelly_schedule_manager/` for this integration; it does not copy the card into `www` or register a dashboard resource. Download the card from this repository separately, including when installing the integration through HACS.

1. Copy `shelly-schedule-card.js` into your Home Assistant `www` directory, creating it if needed:

   ```text
   <config>/www/shelly-schedule-card.js
   ```

   `<config>` is the directory containing `configuration.yaml` (commonly `/config`), so the usual destination is `/config/www/shelly-schedule-card.js`. Home Assistant serves files in `www` under `/local/`: the file above is available at `/local/shelly-schedule-card.js`. See [Home Assistant's file hosting documentation](https://www.home-assistant.io/integrations/http/#hosting-files).

   If you created `www` for the first time, restart Home Assistant. Open `/local/shelly-schedule-card.js` on your Home Assistant address and confirm that it returns JavaScript before adding the resource. A 404 means the file is missing from the served location; check its exact name and path and restart if you just created `www`.

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

The card lists configured Shelly Schedule Manager devices and lets you select which device to manage. Edit each schedule's local name, time, enabled state, and **Repeat** weekday buttons. Names are saved in Home Assistant immediately and are independent of staged schedule changes.

When updating the card, replace the file in `www` separately and refresh the browser cache. You can append a version query to the resource URL, such as `/local/shelly-schedule-card.js?v=0.6.0`, and change it when replacing the file to request a fresh copy.

Press **Review & Save** to see pending changes to times, weekdays, and enabled states, then **Confirm Save to Shelly** to apply them to the selected device. Cancel closes the review and keeps your staged edits. Loading while schedule changes are pending asks for confirmation. Card messages show operation success or failure.

## Save verification

When there are pending changes, Save first reads `Schedule.List` and checks the edited jobs against their last loaded or successfully saved values. If any edited job conflicts, the save stops before writing anything. Otherwise, it sends `Schedule.Update` only for changed jobs, preserving their existing RPC actions, then reads `Schedule.List` again.

A job is marked saved only when its returned `timespec`, `enable`, and unchanged `calls` match the intended state. If some jobs fail verification, successfully verified jobs are marked saved and the others remain unsaved. If updates are interrupted or the verification read fails, changes remain marked unsaved even though the device may have applied them. Load from Shelly to inspect the actual device state before retrying; this discards local edits.

## Backup and restore

1. Press **Back up device** in the card, or **Back up Shelly schedules** on the device page, to snapshot the schedules currently on the Shelly. Unsaved local edits are not included.
2. To restore, load schedules first if needed, then press **Stage restore** in the card or **Stage backup restore** on the device page. This replaces local schedule edits with the backed-up timespecs (including weekdays) and enabled states. The card asks for confirmation before replacing edits.
3. Review the staged changes and press **Review & Save**, then **Confirm Save to Shelly**. Without the card, inspect the entities and press **Save to Shelly**.

One backup is stored per device config entry in Home Assistant's `.storage` under `shelly_schedule_manager_backup_<entry_id>` and survives restarts. Each new backup replaces the previous snapshot; Load and Save do not replace it. The snapshot contains schedule IDs, timespecs, enabled states, and RPC actions. Custom names are stored separately and are not restored from this snapshot.

Staging a restore requires the loaded schedule IDs and RPC actions to match the backup. If either differs, nothing is restored. Restore staging does not contact the Shelly or recreate deleted schedules; saving the staged settings performs the usual conflict checks and verification.

## Network activity

Setup checks connectivity with `Schedule.List`. The integration then reads schedules once on initialization, with no timer-based polling. Each explicit Load or Backup performs a read. A Save with pending changes performs a preflight read, updates changed jobs, and reads back for verification; a Save with no changes makes no device calls. Editing names, times, weekdays, or enabled states and staging a restore do not contact the Shelly.

## Security

The integration connects to the device's local RPC endpoint over HTTP and uses HTTP Digest authentication. Use it on a trusted local network and avoid exposing the device's RPC endpoint to the internet.

## Repository maintenance

The integration lives in `custom_components/shelly_schedule_manager`; `hacs.json` at the repository root supplies its HACS metadata. GitHub Actions runs HACS validation and Home Assistant's hassfest on pushes and pull requests, and can also be run manually.

For a release, update the integration manifest's version and publish a matching GitHub release (for example, manifest version `0.6.1` and tag `v0.6.1`). No ZIP asset is required: HACS downloads the integration directory from the selected ref. The selected branch or release must contain the HACS layout; older releases with the previous layout are not compatible.

HACS validation skips only the external Home Assistant Brands check for custom-repository use. Inclusion in the default HACS catalog is a separate submission and requires a Home Assistant Brands entry and all validation checks to pass. Before submitting, remove `ignore: brands` from the validation workflow. See the [HACS publishing requirements](https://www.hacs.dev/docs/publish/include/).

## API reference

The integration uses Shelly's [Schedule component RPC API](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Schedule/).

## License

This project is licensed under the [MIT License](LICENSE).
