"""Home Assistant diagnostics export, with no additional device reads."""
from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass, entry):
    manager = hass.data[DOMAIN][entry.entry_id]
    return {"schema_version": 1, "device": manager.view(), "history_count": len(manager.history.items)}
