"""Editable per-job labels, stored locally in Home Assistant, not on Shelly."""
from homeassistant.components.text import TextEntity
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
            async_add_entities([entity for job_id in fresh for entity in (ScheduleName(entry, manager, job_id), ScheduleWeekdays(entry, manager, job_id))])

    add_jobs()
    entry.async_on_unload(manager.subscribe(add_jobs))


class ScheduleName(ScheduleEntity, TextEntity):
    _attr_native_min = 0
    _attr_native_max = 80
    _attr_icon = "mdi:rename-box"

    def __init__(self, entry, manager, job_id):
        super().__init__(entry, manager, f"job_{job_id}_name")
        self.job_id = job_id
        self._attr_name = f"Job {job_id} name"

    @property
    def available(self):
        return self.job_id in self.manager.jobs

    @property
    def native_value(self) -> str:
        return self.manager.get_job_name(self.job_id)

    async def async_set_value(self, value: str) -> None:
        if len(value) > 80:
            raise HomeAssistantError("Schedule name is too long (maximum 80 characters)")
        await self.manager.set_job_name(self.job_id, value)


class ScheduleWeekdays(ScheduleEntity, TextEntity):
    """Simple CSV weekday editor, 0=Sunday through 6=Saturday."""
    _attr_native_min = 1
    _attr_native_max = 13
    _attr_icon = "mdi:calendar-week"

    def __init__(self, entry, manager, job_id):
        super().__init__(entry, manager, f"job_{job_id}_days")
        self.job_id = job_id
        self._attr_name = f"Job {job_id} days"

    @property
    def available(self):
        return self.job_id in self.manager.jobs

    @property
    def native_value(self):
        job = self.manager.jobs.get(self.job_id)
        return job.weekday_text if job else None

    @property
    def extra_state_attributes(self):
        job = self.manager.jobs.get(self.job_id)
        return {"editable": job.weekday_values is not None,
                "unsaved_changes": job.dirty,
                "timespec": job.timespec} if job else {}

    async def async_set_value(self, value: str) -> None:
        job = self.manager.jobs.get(self.job_id)
        if job is None:
            raise HomeAssistantError("Job no longer exists. Load from Shelly again.")
        job.set_weekdays(value)
        self.manager.notify()
