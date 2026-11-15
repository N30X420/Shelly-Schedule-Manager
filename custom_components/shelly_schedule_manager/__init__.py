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
from .services import DATA_WORKSPACE, register
from .storage import History, Templates
from .workspace import Workspace


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve both card languages once, independently of device entry lifecycles."""
    templates = Templates(Store(hass, 1, f"{DOMAIN}_templates"))
    await templates.load()
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                f"/{DOMAIN}/{filename}",
                str(Path(__file__).parent / "www" / filename),
                cache_headers=False,
            )
            for filename in ("shelly-schedule-card.js", "shelly-schedule-card-nl.js", "manager-panel.js", "timeline.js")
        ]
    )
    workspace = Workspace(hass, templates)
    hass.data[DATA_WORKSPACE] = workspace
    register(hass, workspace)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = ShellyClient(entry.data["host"], entry.data["username"], entry.data["password"])
    manager = ScheduleManager(hass, client)
    manager.entry_id, manager.title = entry.entry_id, entry.title
    manager.state_store = Store(hass, 1, f"{DOMAIN}_state_{entry.entry_id}")
    state = await manager.state_store.async_load() or {}
    manager.device_id = state.get("device_id")
    manager.last_load, manager.last_save = state.get("last_load"), state.get("last_save")
    manager.journal = state.get("journal")
    manager.recovery_required = bool(manager.journal)
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
    manager.history = History(Store(hass, 1, f"{DOMAIN}_history_{entry.entry_id}"), entry.entry_id)
    await manager.history.load(manager.backup)
    try:
        # Exactly one discovery/read on each integration startup, no polling.
        await manager.load(initial=True)
    except Exception as exc:
        raise ConfigEntryNotReady(f"Could not load schedules from {entry.title}: {exc}") from exc
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    workspace = hass.data[DATA_WORKSPACE]
    workspace.managers[entry.entry_id] = manager
    entry.async_on_unload(manager.subscribe(workspace.notify))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        workspace.managers.pop(entry.entry_id, None)
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    workspace.notify()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if hass.data[DOMAIN][entry.entry_id]._lock.locked():
        return False
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        hass.data[DATA_WORKSPACE].managers.pop(entry.entry_id, None)
        hass.data[DATA_WORKSPACE].notify()
    return ok
