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
- Create, duplicate, and delete jobs through the card's **Manage schedules / Timeline** workspace.
- Save individual jobs or device schedule sets as named templates; preview and stage copies to other devices with switch-channel mapping.
- Inspect a weekly or daily timeline grouped by switch channel, including disabled events and advanced-rule fallbacks.
- Preview bulk template/clone/enable/disable operations, explicitly confirm writes, and follow per-device progress (at most two devices execute concurrently).
- Test connections manually and download redacted diagnostics.
- Keep versioned history, compare snapshots, stage rollback, and configure retention (20 snapshots per device by default).

See [usage and troubleshooting](docs/USAGE.md), [storage and architecture](docs/ARCHITECTURE.md), [release notes](CHANGELOG.md), and the [real-device verification checklist](docs/VERIFY.md).

## Requirements and limitations

- A Shelly Gen2 or Gen3 device with the RPC Schedule API enabled and reachable from Home Assistant's network.
- The device's local RPC username and password.
- The simple time/weekday editor supports six-field cron (`second minute hour day month weekday`). Other cron formats, sunrise/sunset jobs, and arbitrary existing RPC calls are preserved. Advanced times are unavailable through the time helper and appear in the workspace's fallback list; edit their expressions on Shelly.
- Weekday editing supports `*`, individual numeric days, weekday names, and comma-separated lists. Advanced weekday expressions such as ranges or steps are preserved but must be edited on the Shelly. At least one weekday must remain selected.
- New jobs use `Switch.Set` ON/OFF actions, an explicit switch component ID, and device-local time. Shelly documents a maximum of 20 jobs per device. Cloning never reuses a source device's schedule IDs.
- Arbitrary existing actions remain intact. Cross-device cloning/creation and action-changing rollback are supported for `Switch.Set` only; unsupported methods/components are rejected before staging or saving. Custom actions cannot be edited through the simple editor.
- The new workspace, diagnostics and management action require a Home Assistant administrator account. Existing entities and dashboard card types remain available.
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

HACS installs and updates both the integration and its bundled Lovelace card. After configuring a device, add the dashboard resource described below; no separate JavaScript download or copy into `www` is needed. This repository is installed as a custom repository; it is not listed in the default HACS catalog.

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

These entities can be used directly in Home Assistant even if you do not install the optional card. Pressing **Save to Shelly** directly saves ordinary updates. Pending creates, deletes, action changes, or staged name restoration require a full preview and confirmation through the workspace or the `shelly_schedule_manager.manage` action. New jobs get permanent helper entities only after Shelly assigns their IDs. Operation results also appear in Home Assistant notifications.

## Optional Lovelace card

Both card languages are bundled in `custom_components/shelly_schedule_manager/www/`, so HACS and manual integration installations include them. The integration serves them directly once it is set up.

| Language | JavaScript module resource | Card type |
| --- | --- | --- |
| English | `/shelly_schedule_manager/shelly-schedule-card.js` | `custom:shelly-schedule-card` |
| Dutch | `/shelly_schedule_manager/shelly-schedule-card-nl.js` | `custom:shelly-schedule-card-nl` |

Choose the resource and matching card type for your preferred language. The Dutch module imports the shared card code automatically; you only need to add the Dutch resource to use it. Both types can also be used on the same dashboard. Card language is independent of your Home Assistant profile language. Custom device and schedule names are preserved, and error details returned by the integration may still be in English.

1. Install or update the integration, restart Home Assistant, and configure at least one Shelly Schedule Manager device.
2. In **Settings → Dashboards → Resources**, add the English or Dutch resource URL from the table as a **JavaScript module**. Enable **Advanced mode** in your Home Assistant profile if the Resources menu is hidden. For YAML-managed resources, the English example is:

   ```yaml
   lovelace:
     resource_mode: yaml
     resources:
       - url: /shelly_schedule_manager/shelly-schedule-card.js
         type: module
   ```

3. Add a **Manual** card to a dashboard and use:

   ```yaml
   type: custom:shelly-schedule-card
   title: Shelly schedules
   ```

   For Dutch, load the Dutch resource and use:

   ```yaml
   type: custom:shelly-schedule-card-nl
   title: Shelly-schema’s
   ```

The card lists configured Shelly Schedule Manager devices and lets you select which device to manage. Edit each schedule's local name, time, enabled state, and **Repeat** weekday buttons. Names are saved in Home Assistant immediately and are independent of staged schedule changes.

Schedule rows follow the device-assigned job IDs known from the latest Load or verified Save, including disabled jobs. Retained helper entities for removed jobs are hidden, and an empty device shows no schedule rows. Press **Load from Shelly** to pick up changes made directly on the device; there is no fixed default of eight jobs or periodic discovery. Newly staged jobs appear in the management workspace until Save assigns their device IDs.

HACS updates the bundled card with the integration. Restart Home Assistant after updating and refresh the dashboard. The resource is served without Home Assistant's long-lived static cache headers.

If upgrading from the separate card installation, replace the old `/local/shelly-schedule-card.js` resource with your chosen resource URL above. The old copy in `/config/www` is no longer needed. When switching languages, also update the card type; a custom title remains as you entered it. If the new URL returns 404, check that the bundled file exists, restart Home Assistant, and check the integration setup logs.

Press **Review & Save** to see pending changes to times, weekdays, and enabled states, then **Confirm Save to Shelly** to apply them to the selected device. Cancel closes the review and keeps your staged edits. Loading while schedule changes are pending asks for confirmation. Card messages show operation success or failure.

Open **Manage schedules / Timeline** (**Schema’s beheren / Tijdlijn** in Dutch) for the new features. Confirm the configured device selected inside this workspace. Stage creates, duplicates, deletes or restored settings, then press **Preview & Save all changes** and inspect the complete operation list before **Confirm Save to Shelly**. The timeline and per-device bulk progress update through authenticated Home Assistant push messages; they do not poll Shelly. Template application and copying have a separate preview and local staging step before Save. See [the workspace guide](docs/USAGE.md).

To keep the everyday dashboard simpler, hide the management button and its workspace with `management: false`:

```yaml
type: custom:shelly-schedule-card
title: Shelly schedules
management: false
```

This option works with the Dutch card too. Set `management: true` on a separate maintenance card to show the workspace. The default is `true` for existing dashboards. Use YAML booleans without quotes; strings such as `"false"` are rejected. This controls visibility of the advanced workspace; ordinary schedule controls and Home Assistant permissions still apply.

Inside the workspace, **Weekly timeline** is a separate collapsible section, initially closed. Its expanded/collapsed state is preserved while the card updates; opening it shows the day/week controls and chart.

## Save verification

When there are pending changes, Save reads `Schedule.List`, checks edited/deleted jobs against the baseline, and discovers device identity, methods and switch components. If any edited job conflicts, the save stops before writing anything. A deterministic plan deletes first to free capacity, updates existing jobs, then creates new ones without supplying IDs. Save reads `Schedule.List` again to verify the final state. Previews are invalidated by local edits or a changed loaded configuration.

A job is marked saved only when its returned `timespec`, `enable`, and unchanged `calls` match the intended state. If some jobs fail verification, successfully verified jobs are marked saved and the others remain unsaved. If updates are interrupted or the verification read fails, changes remain marked unsaved even though the device may have applied them. Load from Shelly to inspect the actual device state before retrying; this discards local edits.

Assigned IDs and names are retained after successful Create responses, even if a later operation fails. An uncertain Create response is never retried automatically: a durable recovery marker blocks further saves until an explicit Load. Multi-job and multi-device saves are not atomic. Device identity changes also block writes until the device is reconfigured.

## Backup and restore

1. Press **Back up device** in the card, or **Back up Shelly schedules** on the device page, to snapshot the schedules currently on the Shelly. Unsaved local edits are not included.
2. Open **History and rollback** to compare a snapshot with the current editor or another snapshot. **Restore (preview)** shows a proposal; **Stage proposal locally** replaces local edits only. The legacy **Stage restore** button still stages the latest manual backup.
3. Use the workspace's **Preview & Save all changes**, then confirm. Missing jobs are recreated with new device-assigned IDs; obsolete jobs are deleted only by the confirmed Save plan.

The latest manual backup remains at `shelly_schedule_manager_backup_<entry_id>` in Home Assistant's `.storage` for compatibility. Versioned history at `shelly_schedule_manager_history_<entry_id>` records manual backups and completed, verified saves/restores/bulk changes, including friendly names. Existing backups are imported once into history without deleting the original. History defaults to 20 immutable snapshots per device; **Set retention limit** accepts 1–1000. See [storage migration details](docs/ARCHITECTURE.md).

Restoration validates capabilities before staging and again before writing. Unsupported action changes, device conflicts, and capacity violations stop the operation. Sensitive fields are redacted from stored snapshots; snapshots containing redacted action parameters cannot be restored. Templates containing recognized secret fields are rejected.

## Network activity

Setup checks connectivity with `Schedule.List`, and initialization reads schedules once. Explicit Load and Backup read schedules. Save previews, template/clone/restore validation and bulk previews perform explicit reads and capability checks. Test Connection reads identity, methods, component status, schedules and optional timezone metadata. Confirmed Save runs preflight checks, performs only planned writes and reads back. Ordinary helper edits, staging a simple create/duplicate/delete, timeline rendering, workspace subscriptions, cached diagnostics downloads, and a Save with no changes make no device calls. There is no timer-based polling.

## Security

The integration connects to the device's local RPC endpoint over HTTP and uses HTTP Digest authentication. Use it on a trusted local network and avoid exposing the device's RPC endpoint to the internet. Credentials remain in Home Assistant config entries. The management API is authenticated and administrator-only; there is no unauthenticated RPC proxy. Diagnostics use selected metadata and recursive secret redaction, and card content is rendered as text.

## Repository maintenance

The integration lives in `custom_components/shelly_schedule_manager`; `hacs.json` supplies HACS metadata. GitHub Actions runs Python/JavaScript regression tests, HACS validation and Home Assistant's hassfest. Local testing instructions and validation limits are in [VERIFY.md](docs/VERIFY.md).

The proposed release is **0.7.0**, with matching manifest version and proposed tag `v0.7.0`. No ZIP asset is required: HACS downloads the integration directory, including all card modules. Publish only after the GitHub validation checks and [real-device checklist](docs/VERIFY.md) pass. Existing config entries, positive job entity IDs, names, backup files and card resource URLs remain compatible. Installing this release does not automatically write schedules.

HACS validation skips only the external Home Assistant Brands check for custom-repository use. Inclusion in the default HACS catalog is a separate submission and requires a Home Assistant Brands entry and all validation checks to pass. Before submitting, remove `ignore: brands` from the validation workflow. See the [HACS publishing requirements](https://www.hacs.dev/docs/publish/include/).

## API reference

The integration uses Shelly's [Schedule component RPC API](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Schedule/).

## License

This project is licensed under the [MIT License](LICENSE).
