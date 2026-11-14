"""Staged schedule-enabled switches, never write to network on toggle."""
from homeassistant.components.switch import SwitchEntity
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
            async_add_entities([ScheduleEnabled(entry, manager, job_id) for job_id in fresh])

    add_jobs()
    entry.async_on_unload(manager.subscribe(add_jobs))


class ScheduleEnabled(ScheduleEntity, SwitchEntity):
    def __init__(self, entry, manager, job_id):
        super().__init__(entry, manager, f"job_{job_id}_enabled")
        self.job_id = job_id
        self._attr_name = f"Job {job_id} enabled"
        self._attr_icon = "mdi:calendar-check"

    @property
    def available(self):
        return self.job_id in self.manager.jobs

    @property
    def is_on(self):
        job = self.manager.jobs.get(self.job_id)
        return job.enabled if job else None

    @property
    def extra_state_attributes(self):
        job = self.manager.jobs.get(self.job_id)
        return {"action": job.action, "unsaved_changes": job.dirty} if job else {}

    async def async_turn_on(self, **kwargs):
        self._set(True)

    async def async_turn_off(self, **kwargs):
        self._set(False)

    def _set(self, enabled):
        job = self.manager.jobs.get(self.job_id)
        if job is None:
            raise HomeAssistantError("Job no longer exists. Load from Shelly again.")
        job.set_enabled(enabled)
        self.manager.notify()
