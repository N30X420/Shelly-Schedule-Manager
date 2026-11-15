"""In-memory editable schedule staging, with explicit Load and Save operations."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import time
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
            self.dirty = True

    def set_enabled(self, enabled: bool) -> None:
        if enabled != self.enabled:
            self.enabled = enabled
            self.dirty = True

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

    async def save(self) -> int:
        if not self.loaded:
            raise HomeAssistantError("Press Load from Shelly first")
        async with self._lock:
            dirty = [job for job in self.jobs.values() if job.dirty]
            # Saving only modified schedules avoids unnecessary writes.
            for job in dirty:
                params = {"id": job.id, "timespec": job.timespec, "enable": job.enabled}
                try:
                    result = await self.hass.async_add_executor_job(
                        self.client.call, "Schedule.Update", params
                    )
                except ShellyAPIError as exc:
                    self.notify()
                    raise HomeAssistantError(
                        f"Save stopped at job {job.id}; previous jobs may have been updated: {exc}"
                    ) from exc
                job.dirty = False
                self.revision = result.get("rev", self.revision)
                self.notify()
            return len(dirty)
