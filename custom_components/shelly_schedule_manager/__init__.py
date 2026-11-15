"""Shelly Schedule Manager integration."""
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .api import ShellyClient
from .const import DOMAIN, PLATFORMS
from .manager import ScheduleManager


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve both card languages once, independently of device entry lifecycles."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                f"/{DOMAIN}/{filename}",
                str(Path(__file__).parent / "www" / filename),
                cache_headers=False,
            )
            for filename in ("shelly-schedule-card.js", "shelly-schedule-card-nl.js")
        ]
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = ShellyClient(entry.data["host"], entry.data["username"], entry.data["password"])
    manager = ScheduleManager(hass, client)
    # Names are Home Assistant metadata: stored locally and never sent to Shelly.
    manager.name_store = Store(hass, 1, f"{DOMAIN}_names_{entry.entry_id}")
    stored = await manager.name_store.async_load() or {}
    if isinstance(stored, dict):
        manager.job_names = {
            int(key): value for key, value in stored.items()
            if str(key).isdecimal() and isinstance(value, str) and value.strip()
        }
    manager.backup_store = Store(hass, 1, f"{DOMAIN}_backup_{entry.entry_id}")
    saved_backup = await manager.backup_store.async_load()
    if isinstance(saved_backup, dict) and isinstance(saved_backup.get("jobs"), list):
        manager.backup = saved_backup
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
