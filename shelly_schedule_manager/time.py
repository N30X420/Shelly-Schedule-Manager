"""Staged schedule time selectors, never write to network on change."""
from datetime import time
from homeassistant.components.time import TimeEntity
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .entity import ScheduleEntity


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]
    known = set()

    def add_jobs():
        fresh = sorted(set(manager.jobs) - known)
        if fresh:
            known.update(fresh)
            async_add_entities([ScheduleTime(entry, manager, job_id) for job_id in fresh])

    add_jobs()
    entry.async_on_unload(manager.subscribe(add_jobs))


class ScheduleTime(ScheduleEntity, TimeEntity):
    def __init__(self, entry, manager, job_id):
        super().__init__(entry, manager, f"job_{job_id}_time")
        self.job_id = job_id
        self._attr_name = f"Job {job_id} time"
        self._attr_icon = "mdi:clock-outline"

    @property
    def available(self):
        return self.job_id in self.manager.jobs

    @property
    def native_value(self) -> time | None:
        job = self.manager.jobs.get(self.job_id)
        return job.local_time if job else None

    @property
    def extra_state_attributes(self):
        job = self.manager.jobs.get(self.job_id)
        return {"action": job.action, "timespec": job.timespec, "unsaved_changes": job.dirty} if job else {}

    async def async_set_value(self, value: time) -> None:
        job = self.manager.jobs.get(self.job_id)
        if job is None:
            raise HomeAssistantError("Job no longer exists. Load from Shelly again.")
        job.set_time(value)
        self.manager.notify()
