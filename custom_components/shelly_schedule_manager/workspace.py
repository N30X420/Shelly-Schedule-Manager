"""Application previews and bounded, explicitly confirmed multi-device execution."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from uuid import uuid4

from homeassistant.exceptions import HomeAssistantError

from .security import redact


class Workspace:
    def __init__(self, hass, templates):
        self.hass, self.templates = hass, templates
        self.managers = {}
        self.prepared = {}
        self.batches = {}
        self.listeners = []
        self._semaphore = asyncio.Semaphore(2)

    def subscribe(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener) if listener in self.listeners else None

    def notify(self):
        for listener in tuple(self.listeners):
            try:
                listener()
            except Exception:
                # A disconnected browser must never interrupt a device operation.
                if listener in self.listeners:
                    self.listeners.remove(listener)

    def manager(self, entry_id):
        if entry_id not in self.managers:
            raise HomeAssistantError("Device config entry does not belong to this integration or is unloaded")
        return self.managers[entry_id]

    def view(self):
        return {"devices": [m.view() for m in self.managers.values()], "templates": redact(self.templates.list()),
                "history": {key: redact(m.history.list()) if m.history else [] for key, m in self.managers.items()},
                "batches": deepcopy(list(self.batches.values()))}

    async def prepare(self, entry_id, config, replace=False, mapping=None, source="template"):
        manager = self.manager(entry_id)
        fingerprint = manager.fingerprint()
        proposal = await manager.stage_configuration(config, replace, mapping, source, dry_run=True, expected=fingerprint)
        key = uuid4().hex
        # Keep a private immutable source copy; retention/template deletion cannot alter it.
        self.prepared[key] = {"entry_id": entry_id, "fingerprint": fingerprint, "config": deepcopy(config),
                              "replace": replace, "mapping": deepcopy(mapping), "source": source, "preview": proposal}
        # Bound previews; old IDs expire safely instead of growing memory without limit.
        while len(self.prepared) > 100:
            self.prepared.pop(next(iter(self.prepared)))
        return {"application_id": key, "entry_id": entry_id, "preview": proposal}

    async def stage(self, application_id):
        application = self.prepared.get(application_id)
        if application is None:
            raise HomeAssistantError("Application preview expired; preview again")
        manager = self.manager(application["entry_id"])
        count = await manager.stage_configuration(application["config"], application["replace"], application["mapping"],
                                                  application["source"], expected=application["fingerprint"])
        self.prepared.pop(application_id, None)
        return count

    async def bulk_preview(self, entry_ids, operation, config=None, match="", mapping=None):
        if not entry_ids or len(entry_ids) != len(set(entry_ids)) or len(entry_ids) > 100:
            raise HomeAssistantError("Choose between 1 and 100 distinct configured devices")
        if operation not in ("template", "enable", "disable"):
            raise HomeAssistantError("Unsupported bulk operation")
        key = uuid4().hex
        records = []
        async def preview(entry_id):
            async with self._semaphore:
                try:
                    manager = self.manager(entry_id)
                    if manager.pending():
                        raise HomeAssistantError("Device has unsaved changes; Save or Load first")
                    if operation == "template":
                        proposal = await self.prepare(entry_id, config, mapping=mapping, source="bulk")
                    else:
                        desired = manager.configuration()
                        matched = False
                        for job in desired["jobs"]:
                            if not match or manager.get_job_name(job["id"]).casefold() == match.casefold():
                                job["enable"] = operation == "enable"
                                matched = True
                        if not matched:
                            return {"entry_id": entry_id, "status": "skipped", "error": "No matching schedules"}
                        proposal = await self.prepare(entry_id, desired, replace=True, source="bulk")
                    return dict(proposal, status="pending")
                except Exception as exc:
                    return {"entry_id": entry_id, "status": "conflict" if "conflict" in str(exc).lower() else "failed", "error": str(exc)}
        records = await asyncio.gather(*(preview(entry_id) for entry_id in entry_ids))
        identities = {}
        for record in records:
            if record["status"] == "pending":
                physical_id = self.manager(record["entry_id"]).device_id
                identities.setdefault(physical_id, []).append(record)
        for aliases in identities.values():
            if len(aliases) > 1:
                for record in aliases:
                    record.update(status="conflict", error="Selected config entries refer to the same physical device")
        self.batches[key] = {"id": key, "status": "preview", "devices": records}
        while len(self.batches) > 20:
            removable = next((k for k, v in self.batches.items() if v["status"] != "in_progress" and k != key), None)
            if removable is None:
                raise HomeAssistantError("Too many active bulk operations")
            self.batches.pop(removable)
        self.notify()
        return deepcopy(self.batches[key])

    async def bulk_execute(self, batch_id, confirmed):
        if confirmed is not True:
            raise HomeAssistantError("Explicit bulk-write confirmation required")
        batch = self.batches.get(batch_id)
        if not batch or batch["status"] not in ("preview", "queued"):
            raise HomeAssistantError("Bulk preview expired or already executed")
        batch["status"] = "in_progress"
        self.notify()
        async def execute(record):
            if record["status"] != "pending":
                return
            async with self._semaphore:
                record["status"] = "in_progress"
                self.notify()
                try:
                    manager = self.manager(record["entry_id"])
                    await self.stage(record["application_id"])
                    preview = await manager.preview()
                    count = await manager.save(preview["review_id"], source="bulk")
                    record.update(status="success", verified=count)
                except Exception as exc:
                    record.update(status="conflict" if "conflict" in str(exc).lower() or "stale" in str(exc).lower() else "failed", error=str(exc))
                self.notify()
        await asyncio.gather(*(execute(record) for record in batch["devices"]))
        statuses = {r["status"] for r in batch["devices"]}
        batch["status"] = "success" if statuses <= {"success", "skipped"} and "success" in statuses else "partial_or_failed"
        self.notify()
        return deepcopy(batch)
