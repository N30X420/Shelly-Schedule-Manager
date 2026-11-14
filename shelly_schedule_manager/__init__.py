"""Shelly Schedule Manager integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import ShellyClient
from .const import DOMAIN, PLATFORMS
from .manager import ScheduleManager


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = ShellyClient(entry.data["host"], entry.data["username"], entry.data["password"])
    manager = ScheduleManager(hass, client)
    try:
        # Exactly one discovery/read on each integration startup, no polling.
        await manager.load()
    except Exception as exc:
        raise ConfigEntryNotReady(f"Could not load schedules from {entry.title}: {exc}") from exc
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
