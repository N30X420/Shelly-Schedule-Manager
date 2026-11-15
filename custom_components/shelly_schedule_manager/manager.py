"""Manual synchronization, staged job lifecycle and verified deterministic saves."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone, time
import hashlib
import json
from time import perf_counter

from homeassistant.exceptions import HomeAssistantError

from .api import ShellyAPIError
from .capabilities import Capabilities, discover
from .model import Job, parse_job, payload, validate_name
from .security import redact


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class ScheduleManager:
    def __init__(self, hass, client):
        self.hass, self.client = hass, client
        self.jobs = {}
        self.job_names = {}
        self.loaded = False
        self.revision = None
        self.device_id = None
        self.entry_id = None
        self.title = "Shelly"
        self.name_store = self.backup_store = self.state_store = None
        self.backup = None
        self.history = None
        self.capabilities = Capabilities()
        self.diagnostics = {"status": "not_checked"}
        self.last_load = self.last_save = None
        self.recovery_required = False
        self._next_temp = -1
        self._listeners = []
        self._lock = asyncio.Lock()
        self._preview_token = None
        self._save_source = "save"
        self._pending_names = {}
        self.journal = None

    async def rpc(self, method, params=None):
        return await self.hass.async_add_executor_job(self.client.call, method, params)

    def subscribe(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def notify(self):
        for listener in tuple(self._listeners):
            listener()

    def editable(self):
        if not self.loaded:
            raise HomeAssistantError("Load schedules first")
        if self.recovery_required:
            raise HomeAssistantError("Uncertain previous write. Load from Shelly before continuing; do not retry Create")

    def get_job_name(self, job_id):
        return self.job_names.get(job_id, f"Job {job_id}")

    async def persist_names(self, committing=False):
        if self.name_store:
            names = dict(self.job_names)
            if not committing:
                for key, original in self._pending_names.items():
                    if original is None:
                        names.pop(key, None)
                    else:
                        names[key] = original
            await self.name_store.async_save({str(k): v for k, v in names.items() if k >= 0})

    async def persist_state(self):
        if self.state_store:
            await self.state_store.async_save({"device_id": self.device_id, "journal": self.journal,
                                              "last_load": self.last_load, "last_save": self.last_save})

    async def set_job_name(self, job_id, name):
        async with self._lock:
            if job_id not in self.jobs:
                raise HomeAssistantError("Job no longer exists. Load again")
            name = validate_name(name)
            if name:
                self.job_names[job_id] = name
            else:
                self.job_names.pop(job_id, None)
            self._pending_names.pop(job_id, None)
            await self.persist_names()
            self.notify()

    @staticmethod
    def _remote_jobs(result):
        if not isinstance(result, dict) or not isinstance(result.get("jobs"), list):
            raise HomeAssistantError("Invalid schedule listing returned by device")
        jobs = [parse_job(raw) for raw in result["jobs"]]
        if any(j.id < 0 for j in jobs) or len({j.id for j in jobs}) != len(jobs):
            raise HomeAssistantError("Invalid or duplicate device schedule IDs")
        return {j.id: j.raw() for j in jobs}

    @staticmethod
    def _equivalent(raw, timespec, enabled, calls):
        return payload(raw) == {"timespec": timespec, "enable": enabled, "calls": calls}

    async def load(self, initial=False):
        async with self._lock:
            result = await self.rpc("Schedule.List")
            remote = self._remote_jobs(result)
            self.jobs = {key: parse_job(raw) for key, raw in remote.items()}
            for key, original in self._pending_names.items():
                if original is None:
                    self.job_names.pop(key, None)
                else:
                    self.job_names[key] = original
            self.job_names = {k: v for k, v in self.job_names.items() if k >= 0}
            self.revision = result.get("rev")
            self.loaded = True
            self.last_load = utcnow()
            if not initial:
                self.recovery_required = False
                self.journal = None
            self._save_source = "save"
            self._pending_names.clear()
            await self.persist_state()
            self.notify()

    def configuration(self):
        return {"jobs": [j.raw() for j in self.jobs.values() if not j.deleted],
                "names": {str(k): v for k, v in self.job_names.items() if k in self.jobs and not self.jobs[k].deleted}}

    def pending(self):
        changes = [{"id": j.id, "operation": j.operation or "verify", "name": self.get_job_name(j.id),
                 "before": j.baseline, "after": None if j.deleted else j.raw()}
                for j in self.jobs.values() if j.dirty]
        changes.extend({"id": key, "operation": "rename", "name": self.get_job_name(key),
                        "before_name": self._pending_names[key]}
                       for key in sorted(self._pending_names) if key in self.jobs and not self.jobs[key].dirty)
        return changes

    def fingerprint(self):
        return hashlib.sha256(json.dumps({"jobs": [dict(j.raw(), baseline=j.baseline, deleted=j.deleted)
                                                   for j in self.jobs.values()], "names": self.job_names}, sort_keys=True).encode()).hexdigest()

    def view(self):
        return redact({"entry_id": self.entry_id, "title": self.title, "loaded": self.loaded,
                       "jobs": [dict(j.raw(), name=self.get_job_name(j.id), operation=j.operation,
                                     uncertain=j.uncertain, deleted=j.deleted) for j in self.jobs.values()],
                       "pending": self.pending(), "diagnostics": dict(self.diagnostics, host=self.client.host, last_load=self.last_load, last_save=self.last_save),
                       "capabilities": {"switches": sorted(self.capabilities.switches), "capacity": self.capabilities.capacity,
                                        "capacity_source": "Shelly documented limit", "device_id": self.device_id},
                       "recovery_required": self.recovery_required})

    def _stage_new(self, raw, name=""):
        raw = deepcopy(raw)
        raw["id"] = self._next_temp
        job = parse_job(raw)
        job.baseline = None
        self._next_temp -= 1
        self.jobs[job.id] = job
        if name:
            self.job_names[job.id] = validate_name(name)
        return job.id

    async def create(self, name, time_value, weekdays, switch_id, on, enabled=True):
        validate_name(name)
        if type(switch_id) is not int or switch_id < 0 or type(on) is not bool or type(enabled) is not bool:
            raise HomeAssistantError("Invalid switch or enabled state")
        try:
            chosen = time.fromisoformat(time_value)
        except (TypeError, ValueError) as exc:
            raise HomeAssistantError("Invalid time; use HH:MM:SS") from exc
        if chosen.tzinfo or chosen.microsecond:
            raise HomeAssistantError("Use device-local time with whole seconds")
        raw = {"timespec": f"{chosen.second} {chosen.minute} {chosen.hour} * * *", "enable": enabled,
               "calls": [{"method": "Switch.Set", "params": {"id": switch_id, "on": on}}]}
        probe = parse_job(dict(raw, id=-1))
        probe.set_weekdays(weekdays)
        raw["timespec"] = probe.timespec
        async with self._lock:
            self.editable()
            if len(self.configuration()["jobs"]) >= self.capabilities.capacity:
                raise HomeAssistantError("Schedule capacity exceeded")
            new_id = self._stage_new(raw, name)
            self.notify()
            return new_id

    async def duplicate(self, job_id, name=""):
        validate_name(name)
        async with self._lock:
            self.editable()
            job = self.jobs[job_id]
            job.check_editable()
            if len(self.configuration()["jobs"]) >= self.capabilities.capacity:
                raise HomeAssistantError("Schedule capacity exceeded")
            new_id = self._stage_new(job.raw(), name or self.get_job_name(job_id))
            self.notify()
            return new_id

    async def delete(self, job_id, confirmed=False):
        if confirmed is not True:
            raise HomeAssistantError("Confirm deletion after reviewing the device and job")
        async with self._lock:
            self.editable()
            job = self.jobs[job_id]
            job.check_editable()
            if job.id < 0:
                self.jobs.pop(job_id)
                self.job_names.pop(job_id, None)
            else:
                job.deleted = True
            self.notify()

    async def edit(self, job_id, changes):
        if set(changes) - {"time", "weekdays", "enabled", "name", "switch_id", "on"}:
            raise HomeAssistantError("Unsupported editable field")
        async with self._lock:
            self.editable()
            job = deepcopy(self.jobs[job_id])
            job.check_editable()
            if "switch_id" in changes or "on" in changes:
                output = job.switch_output
                if output is None:
                    raise HomeAssistantError("Output editing requires a single Switch.Set action; edit custom actions on Shelly")
                job.set_output(changes.get("switch_id", output["id"]), changes.get("on", output["on"]))
            if "time" in changes:
                try:
                    chosen = time.fromisoformat(changes["time"])
                    if chosen.tzinfo or chosen.microsecond:
                        raise ValueError
                    job.set_time(chosen)
                except (ValueError, TypeError) as exc:
                    raise HomeAssistantError("Invalid device-local time") from exc
            if "weekdays" in changes:
                job.set_weekdays(changes["weekdays"])
            if "enabled" in changes:
                job.set_enabled(changes["enabled"])
            if "name" in changes:
                name = validate_name(changes["name"])
                if name:
                    self.job_names[job_id] = name
                else:
                    self.job_names.pop(job_id, None)
                self._pending_names.pop(job_id, None)
                await self.persist_names()
            self.jobs[job_id] = job
            self.notify()

    async def _preflight(self):
        self.editable()
        remote_result = await self.rpc("Schedule.List")
        remote = self._remote_jobs(remote_result)
        conflicts = [j.id for j in self.jobs.values() if j.dirty and j.id >= 0 and
                     (j.id not in remote or payload(remote[j.id]) != payload(j.baseline))]
        if conflicts:
            raise HomeAssistantError(f"Conflict in jobs {conflicts}. Nothing written; Load and review")
        await discover(self)
        creates = [j for j in self.jobs.values() if j.operation == "create"]
        count = len(remote) - sum(j.operation == "delete" for j in self.jobs.values()) + len(creates)
        if count > self.capabilities.capacity:
            raise HomeAssistantError(f"Schedule capacity exceeded ({self.capabilities.capacity})")
        for j in self.jobs.values():
            if j.operation:
                method = {"create": "Schedule.Create", "update": "Schedule.Update", "delete": "Schedule.Delete"}[j.operation]
                if method not in self.capabilities.methods:
                    raise HomeAssistantError(f"Unsupported method: {method}")
                if j.operation != "delete":
                    # Unchanged custom actions on existing jobs need no reinterpretation.
                    if j.operation == "create" or j.calls != j.baseline["calls"]:
                        self.capabilities.validate([j.raw()], creates=j.operation == "create", action_changes=True)
        return remote

    async def preview(self):
        async with self._lock:
            await self._preflight()
            self._preview_token = self.fingerprint()
            return redact({"review_id": self._preview_token, "changes": self.pending(), "capacity": self.capabilities.capacity,
                           "warning": "Deletes run first. Writes across jobs/devices are not atomic."})

    async def save(self, token=None, source=None):
        async with self._lock:
            self.editable()
            dirty = [j for j in self.jobs.values() if j.dirty]
            renamed = len([key for key in self._pending_names if key in self.jobs and not self.jobs[key].dirty])
            if not dirty and not self._pending_names:
                return 0
            if token is not None and (token != self._preview_token or token != self.fingerprint()):
                raise HomeAssistantError("Preview is stale; preview changes again")
            if token is None and (self._pending_names or any(j.operation != "update" or j.calls != j.baseline["calls"] for j in dirty)):
                raise HomeAssistantError("Preview and confirm structural changes in Manage schedules before saving")
            for job in self.jobs.values():
                job.locked = True
            try:
                await self._preflight()
                # Deterministic order makes room before creates and never reuses source IDs.
                plan = sorted(dirty, key=lambda j: ({"delete": 0, "update": 1, "create": 2}.get(j.operation, 3), j.id))
                error = None
                deleted_verified = set()
                for job in plan:
                    operation = job.operation
                    try:
                        if operation == "create":
                            self.journal = {"operation": "create", "temporary_id": job.id, "started": utcnow()}
                            await self.persist_state()  # Durable before any non-idempotent request.
                            self.recovery_required = True
                            response = await self.rpc("Schedule.Create", payload(job.raw()))
                            assigned = response.get("id")
                            if type(assigned) is not int or assigned < 0 or assigned in self.jobs:
                                raise HomeAssistantError("Create outcome unknown; Load to inspect. Do not retry")
                            previous = job.id
                            del self.jobs[previous]
                            job.id = assigned
                            self.jobs[assigned] = job
                            if previous in self.job_names:
                                self.job_names[assigned] = self.job_names.pop(previous)
                            job.baseline = job.raw()
                            job.uncertain = True
                            self.journal["assigned_id"] = assigned
                            await self.persist_state()
                            await self.persist_names()
                        elif operation == "delete":
                            await self.rpc("Schedule.Delete", {"id": job.id})
                            # IDs may be reused by a subsequent Create. Verify absence
                            # now, before retiring this tombstone or freeing its name.
                            checkpoint = self._remote_jobs(await self.rpc("Schedule.List"))
                            if job.id in checkpoint:
                                raise HomeAssistantError("Delete verification failed; no further writes sent")
                            deleted_verified.add(job.id)
                            self.jobs.pop(job.id, None)
                            self.job_names.pop(job.id, None)
                            self._pending_names.pop(job.id, None)
                        else:
                            await self.rpc("Schedule.Update", dict(payload(job.raw()), id=job.id))
                    except (ShellyAPIError, HomeAssistantError) as exc:
                        if operation == "create":
                            job.uncertain = True
                        error = exc
                        break
                try:
                    result = await self.rpc("Schedule.List")
                    remote = self._remote_jobs(result)
                except (ShellyAPIError, HomeAssistantError) as exc:
                    raise HomeAssistantError("Updates may have applied; read-back failed. Load to inspect before retrying") from exc
                verified = 0
                for job in dirty:
                    if job.deleted and job.id in deleted_verified:
                        verified += 1
                    elif job.deleted and job.id not in remote:
                        self.jobs.pop(job.id, None)
                        self.job_names.pop(job.id, None)
                        verified += 1
                    elif not job.deleted and job.id >= 0 and job.id in remote and payload(job.raw()) == payload(remote[job.id]):
                        job.baseline = deepcopy(remote[job.id])
                        job.uncertain = False
                        verified += 1
                if not any(j.uncertain for j in self.jobs.values()):
                    self.recovery_required = False
                    self.journal = None
                await self.persist_names()
                await self.persist_state()
                self.revision = result.get("rev")
                if error or verified != len(dirty):
                    raise HomeAssistantError(f"Partial save: {verified}/{len(dirty)} verified. {str(error) if error else 'Verification mismatch'}. Load to inspect before retrying")
                await self.persist_names(committing=True)
                self.last_save = utcnow()
                await self.persist_state()
                if self.history:
                    await self.history.record(remote, self.job_names, source or self._save_source)
                self._pending_names.clear()
                self._save_source = "save"
                return verified + renamed
            finally:
                for job in self.jobs.values():
                    job.locked = False
                self._preview_token = None
                self.notify()

    async def make_backup(self, description=""):
        description = validate_name(description)
        async with self._lock:
            raw = self._remote_jobs(await self.rpc("Schedule.List"))
            backup = redact({"created": utcnow(), "jobs": list(raw.values())})
            if not self.backup_store:
                raise HomeAssistantError("Backup storage not configured")
            await self.backup_store.async_save(backup)
            self.backup = backup
            if self.history:
                await self.history.record(raw, self.job_names, "backup", description)
            self.notify()
            return len(raw)

    async def stage_restore(self):
        if not self.backup:
            raise HomeAssistantError("No backup exists")
        return await self.stage_configuration(self.backup, replace=True, source="restore")

    async def stage_configuration(self, config, replace=False, mapping=None, source="template", dry_run=False, expected=None):
        from .security import safe_to_restore
        if not safe_to_restore({"jobs": config.get("jobs", []), "names": config.get("names", {})}):
            raise HomeAssistantError("Snapshot contains redacted secrets and cannot be restored")
        async with self._lock:
            self.editable()
            if expected is not None and expected != self.fingerprint():
                raise HomeAssistantError("Preview is stale; preview changes again")
            if mapping is not None and (not isinstance(mapping, dict) or any(type(v) is not int or v < 0 for v in mapping.values())):
                raise HomeAssistantError("Channel mapping must map source IDs to nonnegative target IDs")
            await self._preflight()
            incoming = []
            names = config.get("names", {})
            restore_names = "names" in config and config.get("names_recorded", True)
            for raw in config["jobs"]:
                raw = parse_job(raw).raw()
                for call in raw["calls"]:
                    params = call.get("params", {})
                    if call["method"].lower() == "switch.set" and mapping:
                        params["id"] = mapping.get(str(params.get("id")), params.get("id"))
                incoming.append(raw)
            # Existing exact-ID actions can be retained on same-device restore.
            for raw in incoming:
                current = self.jobs.get(raw["id"]) if replace else None
                if current is None or current.calls != raw["calls"]:
                    self.capabilities.validate([raw], creates=current is None, action_changes=True)
            final_count = len(incoming) if replace else len(self.configuration()["jobs"]) + len(incoming)
            if final_count > self.capabilities.capacity:
                raise HomeAssistantError("Schedule capacity exceeded; nothing staged")
            proposed = deepcopy(self.jobs)
            proposed_names = deepcopy(self.job_names)
            next_temp = self._next_temp
            if replace:
                for job in proposed.values():
                    job.deleted = True
                proposed = {key: job for key, job in proposed.items() if key >= 0}
            for raw in incoming:
                if replace and raw["id"] in proposed:
                    job = proposed[raw["id"]]
                    job.timespec, job.enabled, job.calls = raw["timespec"], raw["enable"], raw["calls"]
                    job.deleted = False
                    key = job.id
                else:
                    key = next_temp
                    next_temp -= 1
                    job = parse_job(dict(raw, id=key))
                    job.baseline = None
                    proposed[key] = job
                if restore_names and str(raw["id"]) in names:
                    proposed_names[key] = validate_name(names[str(raw["id"])])
                elif replace and restore_names:
                    proposed_names.pop(key, None)
            if dry_run:
                return redact({"jobs": [dict(j.raw(), operation=j.operation, deleted=j.deleted,
                                             name=proposed_names.get(key, f"Job {key}"))
                                        for key, j in proposed.items()],
                               "changes": sum(j.dirty for j in proposed.values()) + sum(
                                   key >= 0 and not j.deleted and proposed_names.get(key) != self.job_names.get(key)
                                   for key, j in proposed.items()),
                               "capacity": self.capabilities.capacity})
            self._next_temp = next_temp
            for key, job in proposed.items():
                if key >= 0 and not job.deleted:
                    original = self._pending_names.get(key, self.job_names.get(key))
                    if proposed_names.get(key) != original:
                        self._pending_names[key] = original
                    else:
                        self._pending_names.pop(key, None)
            self.jobs, self.job_names = proposed, proposed_names
            self._save_source = source
            self.notify()
            return len(self.pending())

    async def test_connection(self):
        async with self._lock:
            started = perf_counter()
            result = {"status": "not_checked", "checked_at": utcnow(), "host": self.client.host}
            try:
                info, status = await discover(self)
                schedules = self._remote_jobs(await self.rpc("Schedule.List"))
                result.update(status="connected", device={key: info.get(key) for key in ("id", "model", "gen", "ver", "fw_id")},
                              device_time=status.get("sys", {}).get("time"), schedule_count=len(schedules),
                              capacity=self.capabilities.capacity, capacity_source="Shelly documented limit")
                if "Sys.GetConfig" in self.capabilities.methods:
                    try:
                        config = await self.rpc("Sys.GetConfig")
                        result["timezone"] = config.get("location", {}).get("tz")
                    except ShellyAPIError:
                        result["metadata_warning"] = "Timezone unavailable"
            except ShellyAPIError as exc:
                result.update(status=exc.kind, last_error=str(exc))
            except HomeAssistantError as exc:
                result.update(status="unsupported_device", last_error=str(exc))
            result["response_ms"] = round((perf_counter() - started) * 1000, 1)
            self.diagnostics = redact(result)
            self.notify()
            return self.diagnostics
