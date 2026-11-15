# Workspace guide

Use either the English or Dutch card resource documented in the README. Sign in as a Home Assistant administrator and open **Manage schedules / Timeline**. Select the configured device inside this workspace and check its title before acting. Existing helper controls and the ordinary time/weekday review remain available above it.

Set `management: false` in the card YAML to hide the advanced workspace and its entry button on an everyday dashboard. Use `management: true` on a maintenance card; the default is `true` for backward compatibility. The setting applies to both languages and accepts only YAML booleans, not quoted strings. It controls this card's presentation, while Home Assistant continues to enforce permissions. Existing basic editing, load/save and backup controls remain available. Disabling the workspace closes its subscription without discarding staged backend changes.

## Create, duplicate, edit and delete

1. Load schedules if the local editor is stale. Load discards pending local changes.
2. **Create job** opens the local editor: enter a name, device-local time, numeric weekdays (`0` Sunday through `6` Saturday), switch component ID, ON/OFF action and enabled state. For weekdays, use values such as `1,2,3,4,5`; at least one is required.
3. **Stage locally** adds the job with a negative temporary identifier. It sends no write to Shelly. The target component and capacity are verified during preview.
4. **Duplicate** copies the selected job's time, enabled state and calls into a new local job. Supply its name when prompted. Duplicating arbitrary non-switch actions is rejected during preview because their target parameters cannot be safely validated.
5. **Edit** changes time, weekdays, enabled state or local name. Leave an advanced time blank and its weekday expression unchanged to preserve it.
6. **Delete** displays the device, name, ID, timespec and calls before staging deletion. Deleting a temporary job simply cancels its creation.
7. Press **Preview & Save all changes**. Review the complete list, including creates and deletes, then **Confirm Save to Shelly**. A final confirmation authorizes writes. If you edit after preview, preview again.

The plan deletes first to free slots, then updates, then creates. Only Shelly assigns permanent IDs. New helpers appear after IDs are known. The documented Schedule API capacity is 20 jobs; external schedules are included in the final capacity check. Writes can partially complete. On error, inspect the result and Load before retrying. An unknown Create result blocks further writes until Load; never duplicate or retry it blindly.

Direct edits to local names are saved immediately in Home Assistant, as before. Names restored from a history/template proposal remain staged until the confirmed Save; Load discards those staged names. Name-only rollback still requires confirmation and records history.

## Templates and cloning

Open **Templates and copying**:

- **Save as Template** asks for a template name and a job ID. Leave the ID blank for the entire current local device schedule set. This captures the editor, including unsaved changes; **Back up device** instead reads actual device state.
- Select a template, then **Apply Template (preview)**. The target is the currently selected workspace device. Enter a channel mapping such as `{"0": 1}` to map source switch 0 to target switch 1. `{}` keeps channel numbers but still validates that each target channel exists.
- Review the proposed jobs, then **Stage proposal locally**. Apply appends new jobs instead of overwriting target IDs. Use **Preview & Save all changes** to separately authorize writes.
- **Rename Template** and **Delete Template** manage the selected persistent template. Templates are limited to 100 entries, with names up to 80 characters.
- **Copy to Device (preview)** asks for a source job ID (blank copies all), uses the target dropdown, and follows the same channel mapping, preview and staging process. Switch the workspace to the target device to review and save its staged jobs.

Cloning never copies device credentials or reuses source IDs. Creating/cloning custom non-`Switch.Set` actions is intentionally unsupported: knowing that a method exists is insufficient to validate its component-specific parameters. Existing custom actions are preserved.

## Timeline

Expand **Weekly timeline** (**Wekelijkse tijdlijn** in Dutch) inside the workspace. It starts collapsed and remembers its expanded state across card updates, keeping the management view compact.

The axis runs from 00:00 to 24:00 in the device's local timezone. Use day/week controls, select a day, or click its heading to focus it. Events are grouped by switch component and show ON/OFF symbols as well as colors. Toggle disabled schedules; disabled events have a dashed style and explicit label. Hover or focus an event for its device/day/channel/name/time details. Click its marker or caption to open the editor.

The chart uses local staged jobs immediately. Midnight events stay on their actual weekdays. It does not infer active relay intervals, account for runtime relay changes, or predict real dates across DST transitions. Sunrise/sunset expressions, ranges/steps, date-limited cron, multiple calls, and timer-like action parameters appear in the advanced fallback list, with their original expressions preserved.

## Bulk management

1. Save or discard existing local changes on the target devices first.
2. Select configured devices, or use **Select All**.
3. Choose the selected template, cloning from the current device, or enable/disable matching schedules. Cloning supports one job or the complete set. Enable/disable matching uses an exact friendly name; an empty match deliberately selects every schedule.
4. **Preview Changes** validates connectivity/authentication, schedules, capabilities and capacity for each device. No writes occur. The preview contains per-device proposed jobs and failures/skips.
5. Inspect the preview and press **Apply to Selected (confirmed writes)**. Explicitly confirm that writes can partially complete across devices.

At most two devices execute at once. Statuses are pending, in progress, success, failed, skipped or conflict. Progress arrives through Home Assistant push messages, without polling devices. A previewed device that acquires local or remote conflicts fails safely. Overall partial/failure results are never reported as complete success. Successfully changed devices record history; failed devices may still have some verified operations applied. Load affected devices and compare history/device state before retrying.

## Diagnostics

**Test Connection** explicitly reads device identity, allowed methods, component status and schedules. It reads timezone only if `Sys.GetConfig` is available. Missing optional fields remain absent/null. The displayed timestamp, duration and categorized status describe the last test, not continuous online availability. View last successful Load/Save timestamps alongside the host, available metadata and documented capacity.

**Download Diagnostics** exports cached, redacted manager information; it makes no device request. Home Assistant's integration diagnostics download uses the same safe view. Device connection credentials, authorization headers and tokens are not included.

## History and rollback

Manual backups and successful verified saves, restores and bulk changes create immutable snapshots. They include jobs, names, timestamps, source operations, schema versions and a diff summary. The workspace's manual backup button accepts an optional description of up to 80 characters. Newest snapshots are displayed first. Use **Compare** against the current local editor or choose another snapshot; the diff includes adds, deletes, time, weekdays, enable flags, actions/parameters and friendly names.

**Restore (preview)** proposes a replacement configuration. Inspect the jobs and counts, then confirm **Stage proposal locally**. This can replace unsaved local edits but does not write to Shelly. A later confirmed Save applies updates/deletes/creates, verifies them and records a new rollback snapshot. Recreated jobs receive new IDs. Existing-ID custom actions can be preserved; unsupported action replacements/recreations are rejected. Snapshots with redacted RPC secrets cannot be restored.

**Set retention limit** stores 1–1000 snapshots per device (default 20). Readers and application previews hold private copies, so deleting/pruning history does not change a proposal already being reviewed. **Delete snapshot** requires confirmation and removes that historical entry permanently.

## Home Assistant action/API

The administrator-only `shelly_schedule_manager.manage` action accepts `action` and a `data` object and can return a response. The card uses the equivalent authenticated `shelly_schedule_manager/manage` WebSocket command and a read-only `shelly_schedule_manager/subscribe` push subscription. Get `entry_id` from a `status` response; do not substitute a host, entity name or device title.

```yaml
action: shelly_schedule_manager.manage
data:
  action: preview
  data:
    entry_id: YOUR_CONFIG_ENTRY_ID
response_variable: proposed
```

After inspecting `proposed.changes`, a separate call to `save` requires that response's `review_id`, the same `entry_id`, and `confirmed: true`. Changed local state invalidates the review ID. Avoid automations that automatically bypass human review of structural changes.

Supported actions: `status`, `load`, `backup`, `restore`, `preview`, `save`, `create`, `edit`, `duplicate`, `delete`, `template_save`, `template_rename`, `template_delete`, `application_preview`, `application_stage`, `history_diff`, `history_delete`, `retention`, `test_connection`, `diagnostics`, `bulk_preview`, `bulk_start`. Exact field schemas are in `services.py`; none accepts an arbitrary RPC method/host.

## Troubleshooting

| Result | Recovery |
| --- | --- |
| Authentication failed | Check device RPC credentials; reconfigure the config entry if necessary. |
| Timeout/network error | Check power, LAN reachability and address; run a manual test. |
| Conflict/stale preview | Load to inspect current state, reapply intended edits and preview again. |
| Capacity exceeded | Stage deliberate deletions or choose fewer cloned jobs; preview again. |
| Unsupported component/method | Supply a valid switch mapping or manage the custom action on Shelly. |
| Device identity changed | Verify the hardware/address; remove and re-add the intended device rather than overwriting a replacement. |
| Unknown create/read-back failure | Do not retry Create. Explicitly Load, inspect the actual jobs and remove unwanted jobs deliberately. |
| Partial bulk result | Review each device separately; success on another device does not imply rollback of failures. |
| Resource 404 | Ensure the release includes all `www` modules, restart HA and inspect setup logs. |
| Workspace cannot open | Use an administrator account and confirm the integration is loaded. |
| Redacted snapshot | Inspect the original device configuration; automatic recreation from redacted calls is disabled. |
