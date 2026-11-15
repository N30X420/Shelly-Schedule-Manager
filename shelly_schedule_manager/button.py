"""Manual Load / Save buttons with per-device UI notifications."""
from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .entity import ScheduleEntity


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [ScheduleButton(entry, manager, op) for op in ("load", "save", "backup", "restore")]
    )


class ScheduleButton(ScheduleEntity, ButtonEntity):
    def __init__(self, entry, manager, operation):
        super().__init__(entry, manager, operation)
        self.operation = operation
        names = {"load": "Load from Shelly", "save": "Save to Shelly",
                 "backup": "Back up Shelly schedules", "restore": "Stage backup restore"}
        icons = {"load": "mdi:download", "save": "mdi:content-save",
                 "backup": "mdi:content-copy", "restore": "mdi:backup-restore"}
        self._attr_name = names[operation]
        self._attr_icon = icons[operation]

    def _notify(self, message: str, *, failed: bool) -> None:
        """Upsert a per-device notification instead of growing an endless list."""
        persistent_notification.async_create(
            self.manager.hass,
            message,
            title=f"Shelly Schedule Manager — {self.entry.title}",
            notification_id=f"{DOMAIN}_{self.entry.entry_id}_result",
        )

    async def async_press(self) -> None:
        operation = self.operation.title()
        try:
            if self.operation == "load":
                # WARNING: Load intentionally discards unsaved local changes.
                await self.manager.load()
                message = f"✅ Loaded {len(self.manager.jobs)} schedules from **{self.entry.title}**."
            elif self.operation == "backup":
                count = await self.manager.make_backup()
                message = f"✅ Backed up {count} schedule(s) from **{self.entry.title}**."
            elif self.operation == "restore":
                count = await self.manager.stage_restore()
                message = (f"✅ Staged {count} schedule changes from backup for "
                           f"**{self.entry.title}**. Review & Save to apply.")
            else:
                updated = await self.manager.save()
                message = (
                    f"✅ Saved {updated} changed schedule(s) to **{self.entry.title}**."
                    if updated
                    else f"ℹ️ **{self.entry.title}**: no pending changes to save."
                )
        except Exception as exc:
            # Network errors, authentication failures, and Shelly RPC errors all
            # become visible in the Home Assistant notification panel.
            self._notify(
                f"❌ **{operation} failed** for **{self.entry.title}**.\n\n"
                f"{str(exc)[:600]}\n\n"
                "Check that the device is online, reachable and using the correct credentials. "
                "If saving several jobs, some may already have been written; load from "
                "the device to inspect the current values before retrying.",
                failed=True,
            )
            raise HomeAssistantError(f"{operation} failed for {self.entry.title}: {exc}") from exc
        else:
            self._notify(message, failed=False)
