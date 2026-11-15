# Changelog

## 0.7.0 — prepared, not published

- Keep backup and restore controls inside the management workspace; simplify the main action row to Load and Review & Save.
- Default new schedules to all seven days and simplify both card languages by removing the editing hint, storage footer and documented-limit note.
- Show current device-assigned schedules instead of stale registered helpers, including empty devices and disabled jobs; estimate card height from the displayed schedule count.
- Add the boolean `management` card option (default `true`) to hide the advanced workspace on everyday dashboards, and put the weekly timeline in its own initially collapsed section.
- Add locally staged create, duplicate and delete operations with temporary IDs, capacity checks, device identity checks, deterministic saves, and read-back verification.
- Persist a recovery journal before non-idempotent Create calls. Preserve returned IDs after partial completion and block uncertain retries until explicit Load.
- Add persistent single-job and schedule-set templates, rename/delete controls, previewed application, switch mapping and device-to-device copying.
- Add versioned per-device history, snapshot comparisons, staged rollback, configurable retention and one-time migration of existing manual backups.
- Add confirmed bulk template/copy/enable/disable operations, per-device progress/results, and a concurrency limit of two.
- Add manual connection diagnostics, categorized failures, optional device metadata and redacted downloads.
- Add day/week timelines, switch-channel grouping, disabled-event filters, event editing and fallback lists for advanced schedules.
- Preserve advanced cron and arbitrary existing RPC calls instead of failing the entire device load.
- Extend both English and Dutch cards through shared bundled modules; existing resource URLs and card types remain valid.
- Add administrator-only Home Assistant action/WebSocket interfaces and automated offline backend/frontend tests.

Upgrade: update through HACS and restart Home Assistant. Existing devices and names require no reconfiguration. Existing backups are copied into bounded history once; their original storage remains intact. Existing dashboard resources keep working. Open **Manage schedules / Timeline** as an administrator for the new controls.

Supported subset: new/cross-device actions are `Switch.Set` only. Existing custom actions remain editable for enable/time where representable, but cannot be recreated or action-remapped by the simple editor. The weekly chart displays events, not inferred relay-active intervals. Local staging is intentionally ephemeral across restarts; saved templates, history, names, identities and recovery markers persist.

Validation and release gates are recorded in [docs/VERIFY.md](docs/VERIFY.md).
