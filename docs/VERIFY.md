# Validation and release checklist

Proposed release: **0.7.0** (`v0.7.0` after validation). No release or remote push is performed by these changes.

## Automated checks

The offline Python tests mock Shelly transport and Home Assistant registration/storage. They do not require physical devices. Install test dependencies in a development environment:

```text
python -m pip install requests voluptuous PyYAML
python -m unittest discover -s tests -v
python -m compileall -q custom_components
```

With Node.js 22 or later, run:

```text
npm test
```

No npm packages are needed. The frontend runner imports the actual ES modules with a minimal DOM stand-in; shared cases test timeline mapping, midnight behavior, disabled events, separate components, complex-rule fallbacks, both card languages, editor/review rendering and HTML-injection resistance. This validates browser logic but is not a real-browser visual/layout test.

Python coverage includes staged create/update/delete/duplicate, capacity, unsupported components, conflicts, stale reviews, partial and uncertain Create responses, retained IDs/names, read-back failure/mismatch, manual diagnostics and categorized transport failures, secret redaction, immutable templates/history, channel mapping, rollback, retention and legacy migration, bulk partial failures, concurrency and action-schema validation. Module distribution, manifest ordering, translations and YAML are also checked.

Local validation: 52 Python tests passed with installed requests/voluptuous/PyYAML. Shared frontend cases passed under V8, and the native Node test runner passed using VS Code's embedded Node runtime with real ES-module imports. Python compilation, JavaScript syntax, and JSON/YAML checks passed. Docker and Home Assistant were not installed locally, so full hassfest/HACS actions and a live HA instance were not run. Those are explicit release gates, not claimed successes.

GitHub Actions now runs Python 3.13 tests, Node 22 tests, hassfest and HACS validation. HACS continues to skip only the external `brands` check for custom-repository use. Default-catalog submission requires a Brands entry and removal of that skip.

## Manual verification on real Shelly Gen3 devices

Use two configured devices, including one with a different available switch-channel set. Back up device schedules before testing.

- [ ] Upgrade from the existing release through HACS, restart HA, and confirm existing config entries, credentials, positive-ID helpers, names, manual backup and both card resource URLs remain intact.
- [ ] Open English and Dutch cards together. Confirm all new modules load, admin access is enforced, mobile layouts remain usable and custom names are rendered safely.
- [ ] Load each device and compare raw Schedule.List output. Include fixed-time, sunrise/sunset, date-limited and multiple-call jobs; confirm advanced jobs remain unchanged.
- [ ] Stage ordinary edits, a new switch job, a duplicate and a deletion. Confirm no device write occurs before Save, negative IDs stay local, and the preview lists every intended operation.
- [ ] Save and inspect actual Schedule.List results. Confirm newly assigned IDs and name mappings, deletion verification, unchanged unrelated calls, and the history snapshot.
- [ ] Edit an existing single-switch job's output ID and ON/OFF action in the management editor. Confirm that staging makes no RPC call, invalid outputs fail preview, `toggle_after`/`tag` survive Save, and custom/multiple-call schedules expose no output editor.
- [ ] Fill near the 20-job limit and test appending a template; test a deliberate delete/create plan at capacity. Confirm excess creates are blocked before writes.
- [ ] Modify an edited job directly on Shelly after Load and after preview. Confirm conflicts prevent writes and require reload/review.
- [ ] Interrupt a multi-job save and a Create response. Confirm actual device state can be loaded, assigned IDs remain where known, and uncertain Create is never blindly retried, including after an HA restart.
- [ ] Save/rename/delete job and device templates. Copy to another device with a valid mapping, reject an invalid channel, and confirm source IDs do not overwrite target jobs.
- [ ] Verify timeline weekday/Sunday mapping, midnight events, disabled filters, channel groups, event tooltips and event-to-editor navigation. Advanced schedules must use fallback labels.
- [ ] Bulk-preview and confirm a template/clone and enable/disable operation across both devices. Disconnect one device and confirm per-device failures and partial overall status, with no automatic rollback of successes.
- [ ] Test valid credentials, wrong credentials, unavailable device, timeout, and missing optional timezone metadata. Verify last-test timestamps and cached diagnostics downloads; search exports/storage for connection passwords and authorization data.
- [ ] Create several history snapshots, compare all changed fields and friendly names, stage rollback with creates/deletes, then Save and verify its new history record.
- [ ] Restore names only and confirm persistence after restart; separately Load before Save and confirm staged restored names are discarded.
- [ ] Confirm the legacy backup is migrated once, retained after migration, and not re-imported after its history entry is deleted. Set a small retention value and confirm pruning leaves an already-previewed proposal stable.
- [ ] Observe logs/network over an idle period. No periodic Schedule.List, background connection tests or automatic schedule writes should occur.

If an error follows a partial save, Load to inspect the actual device before retrying. Record real device model/firmware, HA version, HACS result and redacted diagnostics alongside release validation.
