# Architecture and storage migration

The integration domain stays `shelly_schedule_manager`. Existing config entries and positive schedule entity unique IDs remain unchanged. Home Assistant stages configuration; devices execute their own schedules.

## Responsibilities

| Module | Responsibility |
| --- | --- |
| `api.py` | Synchronous Digest transport run through HA's executor; typed, sanitized RPC failures. |
| `model.py` | Arbitrary schedule preservation, simple helper editing, create/update/delete detection, snapshot diff. |
| `manager.py` | Per-device staging/locking, preflight conflict detection, save ordering, ID remapping, recovery journal, verification and diagnostics. |
| `capabilities.py` | Explicit identity/method/component discovery and conservative validation of transferable actions. |
| `storage.py` | Bounded, versioned templates/history; immutable reader copies and legacy backup migration. |
| `workspace.py` | Immutable application previews, stale-state checks, bounded bulk execution and push progress. |
| `services.py` | Validated administrator-only action/WebSocket boundary with integration-entry ownership checks. |
| `diagnostics.py` / `security.py` | Cached HA diagnostics export and recursive secret redaction. |
| `button.py`, `time.py`, `switch.py`, `text.py`, `entity.py` | Existing manual buttons and helpers, with preserved positive-ID identity. |
| `www/manager-panel.js` | Shared English/Dutch management interface using safe DOM text creation. |
| `www/timeline.js` | Pure weekly event projection and responsive channel-grouped timeline. |
| `www/shelly-schedule-card*.js` | Existing language-specific card types and bundled entry modules. |

All reads and writes are user-triggered except the existing initialization read. Network requests use HA's executor, while locks, storage and frontend APIs are asynchronous. Frontend subscriptions publish in-memory changes; no coordinator, update interval or timer polls a device. The class metadata `local_polling` describes pull transport, not a periodic schedule.

## Staging and save consistency

New jobs receive monotonically decreasing local negative IDs for the current editor lifetime. Positive IDs always come from Shelly. The baseline contains the last loaded or verified timespec, enabled state and complete calls. Update detection includes RPC parameter changes; deletes retain their baseline until absence is verified. Helpers are not created for temporary IDs. Advanced expressions remain intact and have unavailable time helpers when necessary.

Each device has one async lock for local edits, validation, Load, Save, backup and diagnostics. Helper edits use that same lock. A Save freezes current jobs, rejects stale review IDs, checks remote baselines and capabilities, verifies final capacity, then runs deletes, updates and creates in deterministic order. Existing unaffected remote schedules are not overwritten. Deletes run first, so a later failure can leave deletions applied; the preview warns that the batch is not atomic.

Before each Create, a durable journal is persisted. The request never supplies a desired ID. A returned ID immediately replaces the temporary ID and remaps its friendly name before subsequent writes. After the batch, Schedule.List verifies all completed outcomes. Unverified/unknown creates block further editing/saving until explicit Load, including after a restart. Initial startup reads do not silently clear a recovery marker. A failed read-back never causes an automatic Create retry.

Deletes have an additional Schedule.List checkpoint before the plan proceeds. Only a verified absence retires the tombstone, so a later Create can safely reuse that ID. Conflict checks are preflight reads, not an atomic compare-and-swap operation; avoid concurrent external editors while saving.

Application previews retain private copies of source configurations and a fingerprint of the destination editor. Later template edits/deletion or history pruning cannot alter the proposal. Staging checks that fingerprint and validates again; saving requires a fresh complete review and preflight. Source IDs never map directly onto unrelated target-device IDs. Same-device rollback may update IDs that still exist; missing IDs produce fresh creates instead.

Bulk execution uses one shared semaphore of two for both validation and writes, with a record per configured entry. Each device is independently revalidated after confirmation. Partial outcomes retain successful verified jobs and failed/conflicted status. Disconnected browser listeners cannot abort device execution. Bulk status is temporary, bounded to 20 recent batches; application previews are bounded to 100. No cross-device transaction or automatic rollback is implied.

## Persistent storage

All files below are Home Assistant `Store` entries in `.storage`; do not edit them while HA is running.

| Storage key | Content and compatibility |
| --- | --- |
| `shelly_schedule_manager_names_<entry_id>` | Existing friendly-name mapping; unchanged key and version. |
| `shelly_schedule_manager_backup_<entry_id>` | Existing latest-manual-backup format, retained for legacy buttons. New backups redact sensitive fields. |
| `shelly_schedule_manager_history_<entry_id>` | Schema 1, retention setting, one-time migration flag, immutable snapshots. Default retention 20; configurable 1–1000. |
| `shelly_schedule_manager_templates` | Schema 1 templates with IDs, type, names, jobs/calls, creation/modification timestamps; at most 100 templates. |
| `shelly_schedule_manager_state_<entry_id>` | Bound physical device ID, last Load/Save timestamps, and minimal in-flight Create journal. No credentials or RPC parameters are needed in the journal. |

On first load, an existing manual backup is copied into history with a deterministic migration ID and source `legacy_backup`. The original backup file is left untouched. A stored migration marker prevents re-import after retention pruning or user deletion. Legacy backups do not contain friendly names: migration marks names as unrecorded, and restoring them preserves existing names for jobs that still exist instead of erasing them. Config entries, credentials and entity registry IDs are not migrated or rewritten.

Snapshots contain schema version, ID, entry identifier, timestamp, source, complete jobs, available friendly names, description and diff summary. Storage serializes private copies; existing snapshots are never edited. Retention removes stored records only after readers/previews have copied them. Recognized sensitive fields are redacted; a snapshot whose action configuration is redacted is marked non-restorable. Templates with recognized secret fields are rejected rather than saving unusable action parameters.

Staged job changes remain in memory, as in previous releases. Templates, history, committed names, identities, timestamps and recovery markers survive restarts. Normal local names persist immediately; names staged by rollback are held until confirmed Save and are reverted by Load.

## Compatibility and supported limits

The English resource `/shelly_schedule_manager/shelly-schedule-card.js`, Dutch `.../shelly-schedule-card-nl.js`, and their existing `custom:` types stay unchanged. HACS ships all four frontend modules inside the integration. No dashboard is modified automatically. After upgrade, restart HA and refresh the dashboard.

New and cross-device jobs are restricted to `Switch.Set`: method availability alone cannot prove that arbitrary action parameters point to valid target components. Existing arbitrary actions are preserved during supported enable/time/weekday edits. Restores that would recreate or replace unsupported custom actions are rejected. Secret-bearing snapshots are retained as redacted troubleshooting evidence but cannot be blindly restored.

The management editor can also stage output ID and ON/OFF changes for a job with one valid `Switch.Set` call. It preserves other call parameters and requires explicit preview/Save plus output capability validation. Existing output updates require `Schedule.Update`, independently of whether the device/user permits `Schedule.Create`. Custom/multiple-call jobs cannot be converted by this editor.

The 20-job capacity comes from the [official Shelly Schedule documentation](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Schedule/), not an invented per-model discovery field. The UI labels it as a documented limit. Capability discovery uses [Shelly.GetDeviceInfo, Shelly.ListMethods and Shelly.GetStatus](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Shelly/); optional timezone configuration is queried only if advertised. HA actions use the [administrator service registration helper](https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/service.py), and static assets use the [async static path API](https://contributors.home-assistant.io/blog/2024/06/18/async_register_static_paths/).
