"""Common properties for schedule manager entities."""
from homeassistant.helpers.entity import Entity
from .const import DOMAIN


class ScheduleEntity(Entity):
    _attr_should_poll = False

    def __init__(self, entry, manager, suffix: str) -> None:
        self.entry = entry
        self.manager = manager
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Shelly",
            "model": "Schedule Manager",
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.manager.subscribe(self.async_write_ha_state))
