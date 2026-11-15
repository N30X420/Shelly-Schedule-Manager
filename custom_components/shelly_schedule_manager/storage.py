"""Versioned, bounded template and history stores using Home Assistant Store."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL

from homeassistant.exceptions import HomeAssistantError

from .model import parse_job, snapshot_diff, validate_name
from .security import redact, safe_to_restore


def stamp():
    return datetime.now(timezone.utc).isoformat()


class Templates:
    def __init__(self, store):
        self.store = store
        self.items = {}
        self._lock = asyncio.Lock()

    async def load(self):
        stored = await self.store.async_load() or {}
        self.items = deepcopy(stored.get("templates", {}))

    def list(self):
        return deepcopy(sorted(self.items.values(), key=lambda v: (v["name"].casefold(), v["id"])))

    def get(self, template_id):
        if template_id not in self.items:
            raise HomeAssistantError("Template no longer exists")
        return deepcopy(self.items[template_id])

    async def save(self, name, config, single=False):
        name = validate_name(name)
        if not name:
            raise HomeAssistantError("A template name is required")
        if not safe_to_restore(config):
            raise HomeAssistantError("Templates cannot contain secrets or redacted RPC parameters")
        jobs = [parse_job(j).raw() for j in config["jobs"]]
        if not jobs or len(jobs) > 20 or (single and len(jobs) != 1):
            raise HomeAssistantError("Choose one job or a nonempty schedule set of at most 20 jobs")
        names = {str(k): validate_name(v) for k, v in config.get("names", {}).items()}
        async with self._lock:
            if len(self.items) >= 100:
                raise HomeAssistantError("Template limit reached (100); delete an unused template")
            key = uuid4().hex
            item = {"id": key, "schema_version": 1, "name": name, "type": "job" if single else "set",
                    "created": stamp(), "modified": stamp(), "jobs": jobs, "names": names}
            updated = dict(self.items, **{key: item})
            await self.store.async_save({"schema_version": 1, "templates": updated})
            self.items = updated
            return key

    async def rename(self, template_id, name):
        name = validate_name(name)
        if not name:
            raise HomeAssistantError("A template name is required")
        async with self._lock:
            item = self.get(template_id)
            item.update(name=name, modified=stamp())
            updated = dict(self.items, **{template_id: item})
            await self.store.async_save({"schema_version": 1, "templates": updated})
            self.items = updated

    async def delete(self, template_id):
        async with self._lock:
            self.get(template_id)
            updated = dict(self.items)
            del updated[template_id]
            await self.store.async_save({"schema_version": 1, "templates": updated})
            self.items = updated


class History:
    def __init__(self, store, entry_id):
        self.store, self.entry_id = store, entry_id
        self.limit = 20
        self.items = []
        self._lock = asyncio.Lock()

    async def load(self, legacy=None):
        stored = await self.store.async_load() or {}
        self.items = deepcopy(stored.get("snapshots", []))
        self.limit = stored.get("retention", 20)
        if type(self.limit) is not int or not 1 <= self.limit <= 1000:
            self.limit = 20
        migration_id = uuid5(NAMESPACE_URL, self.entry_id + ":legacy-backup").hex
        if legacy is not None and not stored.get("legacy_migrated"):
            clean = redact(legacy)
            self.items.append({"id": migration_id, "device": self.entry_id, "timestamp": clean.get("created", stamp()),
                               "source": "legacy_backup", "schema_version": 1, "jobs": clean.get("jobs", []),
                               "names": {}, "names_recorded": False, "description": "Migrated pre-0.7 backup", "restorable": safe_to_restore(clean), "diff": []})
            await self._persist(self.items[-self.limit:])

    async def _persist(self, items):
        await self.store.async_save({"schema_version": 1, "retention": self.limit,
                                    "legacy_migrated": True, "snapshots": items})
        self.items = deepcopy(items)

    def list(self):
        return deepcopy(list(reversed(self.items)))

    def get(self, snapshot_id):
        item = next((s for s in self.items if s["id"] == snapshot_id), None)
        if item is None:
            raise HomeAssistantError("Snapshot no longer exists")
        # Readers hold private copies; retention cannot mutate a snapshot in use.
        return deepcopy(item)

    async def record(self, jobs, names, source, description=""):
        async with self._lock:
            config = {"jobs": deepcopy(list(jobs.values())), "names": {str(k): v for k, v in names.items() if k in jobs}}
            clean = redact(config)
            snapshot = dict(clean, id=uuid4().hex, device=self.entry_id, timestamp=stamp(), source=source,
                            schema_version=1, description=validate_name(description), restorable=safe_to_restore(config),
                            diff=snapshot_diff(self.items[-1] if self.items else {"jobs": []}, clean))
            await self._persist((self.items + [snapshot])[-self.limit:])
            return snapshot["id"]

    async def delete(self, snapshot_id):
        async with self._lock:
            self.get(snapshot_id)
            await self._persist([s for s in self.items if s["id"] != snapshot_id])

    async def retention(self, limit):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise HomeAssistantError("Retention must be between 1 and 1000")
        async with self._lock:
            previous = self.limit
            self.limit = limit
            try:
                await self._persist(self.items[-limit:])
            except Exception:
                self.limit = previous
                raise
