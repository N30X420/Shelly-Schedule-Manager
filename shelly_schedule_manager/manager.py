"""In-memory editable schedule staging, with explicit Load and Save operations."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import time, datetime, timezone
from copy import deepcopy
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import ShellyAPIError, ShellyClient


@dataclass
class Job:
    id: int
    timespec: str
    enabled: bool
    calls: list[dict[str, Any]]
    dirty: bool = False
    original_timespec: str = ""
    original_enabled: bool | None = None

    def __post_init__(self) -> None:
        self.original_timespec = self.timespec
        self.original_enabled = self.enabled

    def _refresh_dirty(self) -> None:
        self.dirty = (self.timespec != self.original_timespec or
                      self.enabled != self.original_enabled)

    @property
    def weekday_values(self) -> set[int] | None:
        """Represent simple day-of-week expressions only; preserve advanced cron."""
        fields = self.timespec.split()
        if len(fields) != 6:
            return None
        field = fields[5].strip().upper()
        if field == "*":
            return set(range(7))
        aliases = {"SUN": 0, "MON": 1, "TUE": 2, "WED": 3,
                   "THU": 4, "FRI": 5, "SAT": 6}
        values = set()
        for fragment in field.split(","):
            if not fragment:
                return None
            if fragment.isdecimal() and 0 <= int(fragment) <= 7:
                values.add(int(fragment) % 7)
            elif fragment in aliases:
                values.add(aliases[fragment])
            else:
                return None
        return values or None

    @property
    def weekday_text(self) -> str:
        values = self.weekday_values
        return ",".join(str(day) for day in sorted(values)) if values is not None else "advanced"

    def set_weekdays(self, value: str) -> None:
        if self.weekday_values is None:
            raise HomeAssistantError("Advanced weekday cron expression: edit it on Shelly")
        tokens = value.split(",")
        if not tokens or any(not t.isdecimal() or int(t) > 6 for t in tokens):
            raise HomeAssistantError("Choose at least one weekday (0=Sun, 1=Mon, ... 6=Sat)")
        days = {int(t) for t in tokens}
        if not days:
            raise HomeAssistantError("At least one weekday is required")
        fields = self.timespec.split()
        fields[5] = "0,1,2,3,4,5,6" if len(days) == 7 else ",".join(str(x) for x in sorted(days))
        self.timespec = " ".join(fields)
        self._refresh_dirty()

    @property
    def local_time(self) -> time:
        fields = self.timespec.split()
        return time(int(fields[2]), int(fields[1]), int(fields[0]))

    def set_time(self, new: time) -> None:
        fields = self.timespec.split()
        if len(fields) != 6 or any(not f.isdecimal() for f in fields[:3]):
            raise HomeAssistantError("This job uses a non-fixed time; editing it is not supported")
        fields[:3] = [str(new.second), str(new.minute), str(new.hour)]
        updated = " ".join(fields)
        if updated != self.timespec:
            self.timespec = updated
            self._refresh_dirty()

    def set_enabled(self, enabled: bool) -> None:
        if enabled != self.enabled:
            self.enabled = enabled
            self._refresh_dirty()

    @property
    def action(self) -> str:
        if len(self.calls) == 1 and self.calls[0].get("method", "").lower() == "switch.set":
            params = self.calls[0].get("params", {})
            return f"Switch {params.get('id', 0)} {'ON' if params.get('on') else 'OFF'}"
        return "Custom action"


def parse_job(raw: dict[str, Any]) -> Job:
    try:
        fields = raw["timespec"].split()
        if len(fields) != 6:
            raise ValueError("Expected a six-field cron expression")
        # Only fixed HH:MM:SS can be represented by Home Assistant's time entity.
        hh, mm, ss = (int(fields[i]) for i in (2, 1, 0))
        time(hh, mm, ss)
        return Job(
            id=int(raw["id"]),
            timespec=raw["timespec"],
            enabled=bool(raw["enable"]),
            calls=list(raw.get("calls", [])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ShellyAPIError(f"Unsupported schedule job: {raw!r}") from exc


class ScheduleManager:
    def __init__(self, hass: HomeAssistant, client: ShellyClient) -> None:
        self.hass = hass
        self.client = client
        self.jobs: dict[int, Job] = {}
        self.loaded = False
        self.revision: int | None = None
        self.job_names: dict[int, str] = {}
        self.name_store = None
        self.backup_store = None
        self.backup: dict[str, Any] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._lock = asyncio.Lock()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def get_job_name(self, job_id: int) -> str:
        return self.job_names.get(job_id, f"Job {job_id}")

    async def set_job_name(self, job_id: int, name: str) -> None:
        if job_id not in self.jobs:
            raise HomeAssistantError("Job no longer exists. Load from Shelly again.")
        name = name.strip()
        if not name:
            self.job_names.pop(job_id, None)
        else:
            self.job_names[job_id] = name
        if self.name_store is not None:
            await self.name_store.async_save({str(k): v for k, v in self.job_names.items()})
        self.notify()

    async def load(self) -> None:
        async with self._lock:
            try:
                result = await self.hass.async_add_executor_job(self.client.list_jobs)
                jobs = [parse_job(raw) for raw in result["jobs"]]
                if len({job.id for job in jobs}) != len(jobs):
                    raise ShellyAPIError("Duplicate schedule IDs")
            except ShellyAPIError as exc:
                raise HomeAssistantError(str(exc)) from exc
            self.jobs = {job.id: job for job in jobs}
            self.revision = result.get("rev")
            self.loaded = True
            self.notify()

    @staticmethod
    def _remote_jobs(result: dict[str, Any]) -> dict[int, dict[str, Any]]:
        jobs = result["jobs"]
        by_id = {int(raw["id"]): raw for raw in jobs}
        if len(by_id) != len(jobs):
            raise ShellyAPIError("Duplicate schedule IDs")
        return by_id

    @staticmethod
    def _equivalent(raw: dict[str, Any], timespec: str, enabled: bool,
                    calls: list[dict[str, Any]]) -> bool:
        return (raw.get("timespec") == timespec and
                raw.get("enable") is enabled and raw.get("calls", []) == calls)

    async def make_backup(self) -> int:
        """Store one explicit snapshot, never silently overwrite on Load or Save."""
        async with self._lock:
            try:
                result = await self.hass.async_add_executor_job(self.client.list_jobs)
                raw = self._remote_jobs(result)
                for job in raw.values():
                    parse_job(job)
            except (ShellyAPIError, ValueError, KeyError, TypeError) as exc:
                raise HomeAssistantError(f"Could not back up Shelly: {exc}") from exc
            backup = {
                "created": datetime.now(timezone.utc).isoformat(),
                "jobs": deepcopy(list(raw.values())),
                "rev": result.get("rev"),
            }
            if self.backup_store is None:
                raise HomeAssistantError("Backup storage is not configured")
            await self.backup_store.async_save(backup)
            self.backup = backup
            self.notify()
            return len(raw)

    async def stage_restore(self) -> int:
        """Restore times and enable flags into helpers only; Save still required."""
        if not self.loaded:
            raise HomeAssistantError("Load schedules first")
        async with self._lock:
            if not self.backup or not self.backup.get("jobs"):
                raise HomeAssistantError("No backup exists for this Shelly")
            snapshot = self._remote_jobs({"jobs": self.backup["jobs"]})
            if set(snapshot) != set(self.jobs):
                raise HomeAssistantError("Schedule IDs differ from backup. Nothing restored")
            for job_id, raw in snapshot.items():
                current = self.jobs[job_id]
                if raw.get("calls", []) != current.calls:
                    raise HomeAssistantError(
                        f"Job {job_id} action differs from backup. Nothing restored")
                parse_job(raw)
            count = 0
            for job_id, raw in snapshot.items():
                job = self.jobs[job_id]
                if job.timespec != raw["timespec"] or job.enabled != raw["enable"]:
                    count += 1
                job.timespec = raw["timespec"]
                job.enabled = raw["enable"]
                job._refresh_dirty()
            self.notify()
            return count

    async def save(self) -> int:
        if not self.loaded:
            raise HomeAssistantError("Press Load from Shelly first")
        async with self._lock:
            dirty = [job for job in self.jobs.values() if job.dirty]
            if not dirty:
                return 0
            # Conflict detection: do not overwrite a job changed outside HA.
            try:
                before = await self.hass.async_add_executor_job(self.client.list_jobs)
                remote = self._remote_jobs(before)
            except (ShellyAPIError, ValueError, KeyError, TypeError) as exc:
                raise HomeAssistantError(f"Cannot check device state before save: {exc}") from exc
            conflicts = [job.id for job in dirty if (
                job.id not in remote or not self._equivalent(
                    remote[job.id], job.original_timespec,
                    job.original_enabled, job.calls))]
            if conflicts:
                raise HomeAssistantError(
                    f"External change detected in job(s) {conflicts}. "
                    "Nothing saved. Load from Shelly, review changes, and retry."
                )
            # Multiple RPC updates are NOT atomic. On failure, do not mark jobs clean:
            # the device may have applied an update before the connection failed.
            sent = []
            try:
                for job in dirty:
                    await self.hass.async_add_executor_job(
                        self.client.call, "Schedule.Update",
                        {"id": job.id, "timespec": job.timespec, "enable": job.enabled}
                    )
                    sent.append(job.id)
            except ShellyAPIError as exc:
                self.notify()
                raise HomeAssistantError(
                    f"Save interrupted at job {job.id} after sending {sent}: {exc}. "
                    "Some changes may have been applied; load to inspect before retrying."
                ) from exc
            # Verify final state before clearing *any* dirty flags.
            try:
                after = await self.hass.async_add_executor_job(self.client.list_jobs)
                verified = self._remote_jobs(after)
            except (ShellyAPIError, ValueError, KeyError, TypeError) as exc:
                raise HomeAssistantError(
                    f"Updates sent but read-back verification failed: {exc}. "
                    "Changes remain marked unsaved; load to inspect."
                ) from exc
            mismatched = [job.id for job in dirty if (
                job.id not in verified or not self._equivalent(
                    verified[job.id], job.timespec, job.enabled, job.calls))]
            # Jobs successfully verified become the new baseline, even if other
            # jobs failed verification. This supports safe selective retry.
            for job in dirty:
                if job.id not in mismatched:
                    job.original_timespec = job.timespec
                    job.original_enabled = job.enabled
                    job.dirty = False
            self.revision = after.get("rev", self.revision)
            self.notify()
            if mismatched:
                raise HomeAssistantError(
                    f"Save verification failed for job(s) {mismatched}; "
                    "other verified jobs were saved. Load to inspect the device."
                )
            return len(dirty)
