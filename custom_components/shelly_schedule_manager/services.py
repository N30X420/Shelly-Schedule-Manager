"""Admin-only Home Assistant actions and authenticated push-based card workspace."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.components import persistent_notification, websocket_api
from homeassistant.core import SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN
from .api import ShellyAPIError
from .model import snapshot_diff
from .security import redact

DATA_WORKSPACE = f"{DOMAIN}_workspace"

# All identifiers refer to this integration's config entries, not arbitrary hosts.
SCHEMAS = {
    "status": {},
    "load": {vol.Required("entry_id"): str},
    "backup": {vol.Required("entry_id"): str, vol.Optional("description", default=""): str},
    "restore": {vol.Required("entry_id"): str, vol.Required("confirmed"): vol.All(bool, vol.In([True]))},
    "preview": {vol.Required("entry_id"): str},
    "save": {vol.Required("entry_id"): str, vol.Required("review_id"): str, vol.Required("confirmed"): vol.All(bool, vol.In([True]))},
    "create": {vol.Required("entry_id"): str, vol.Required("name"): str, vol.Required("time"): str,
               vol.Required("weekdays"): str, vol.Required("switch_id"): vol.All(int, vol.Range(min=0)),
               vol.Required("on"): bool, vol.Required("enabled"): bool},
    "edit": {vol.Required("entry_id"): str, vol.Required("job_id"): int, vol.Required("changes"): dict},
    "duplicate": {vol.Required("entry_id"): str, vol.Required("job_id"): int, vol.Optional("name", default=""): str},
    "delete": {vol.Required("entry_id"): str, vol.Required("job_id"): int, vol.Required("confirmed"): vol.All(bool, vol.In([True]))},
    "template_save": {vol.Required("entry_id"): str, vol.Required("name"): str, vol.Optional("job_id"): int},
    "template_rename": {vol.Required("template_id"): str, vol.Required("name"): str},
    "template_delete": {vol.Required("template_id"): str, vol.Required("confirmed"): vol.All(bool, vol.In([True]))},
    "application_preview": {vol.Required("entry_id"): str, vol.Required("source"): vol.In(["template", "history", "clone"]),
                            vol.Optional("template_id"): str, vol.Optional("snapshot_id"): str,
                            vol.Optional("source_entry_id"): str, vol.Optional("job_id"): int,
                            vol.Optional("mapping", default={}): dict},
    "application_stage": {vol.Required("application_id"): str, vol.Required("confirmed"): vol.All(bool, vol.In([True]))},
    "history_diff": {vol.Required("entry_id"): str, vol.Required("snapshot_id"): str, vol.Optional("other_id"): str},
    "history_delete": {vol.Required("entry_id"): str, vol.Required("snapshot_id"): str, vol.Required("confirmed"): vol.All(bool, vol.In([True]))},
    "retention": {vol.Required("entry_id"): str, vol.Required("limit"): vol.All(int, vol.Range(min=1, max=1000))},
    "test_connection": {vol.Required("entry_id"): str},
    "diagnostics": {vol.Required("entry_id"): str},
    "bulk_preview": {vol.Required("entry_ids"): [str], vol.Required("operation"): vol.In(["template", "enable", "disable"]),
                     vol.Optional("template_id"): str, vol.Optional("source_entry_id"): str,
                     vol.Optional("job_id"): int, vol.Optional("match", default=""): str, vol.Optional("mapping", default={}): dict},
    "bulk_start": {vol.Required("batch_id"): str, vol.Required("confirmed"): vol.All(bool, vol.In([True]))},
}


def source_configuration(workspace, data):
    if data.get("template_id"):
        return workspace.templates.get(data["template_id"])
    source = workspace.manager(data["source_entry_id"])
    source.editable()
    config = source.configuration()
    if "job_id" in data:
        config["jobs"] = [j for j in config["jobs"] if j["id"] == data["job_id"]]
        if not config["jobs"]:
            raise HomeAssistantError("Source job no longer exists")
    return config


async def dispatch(workspace, action, data):
    if action not in SCHEMAS:
        raise HomeAssistantError("Unsupported manager action")
    try:
        data = vol.Schema(SCHEMAS[action])(data)
    except vol.Invalid as exc:
        raise HomeAssistantError("Invalid action parameters") from exc
    manager = workspace.manager(data["entry_id"]) if "entry_id" in data else None
    if "job_id" in data and type(data["job_id"]) is not int:
        raise HomeAssistantError("Job ID must be an integer")
    result = {}
    if action == "status":
        return workspace.view()
    if action in ("load", "backup", "restore", "preview", "save", "test_connection"):
        if action == "load":
            await manager.load()
        elif action == "backup":
            result = {"count": await manager.make_backup(data["description"])}
        elif action == "restore":
            result = {"count": await manager.stage_restore()}
        elif action == "preview":
            result = await manager.preview()
        elif action == "save":
            result = {"verified": await manager.save(data["review_id"])}
        else:
            result = await manager.test_connection()
    elif action == "create":
        result = {"id": await manager.create(data["name"], data["time"], data["weekdays"], data["switch_id"], data["on"], data["enabled"])}
    elif action == "edit":
        await manager.edit(data["job_id"], data["changes"])
    elif action == "duplicate":
        result = {"id": await manager.duplicate(data["job_id"], data["name"])}
    elif action == "delete":
        await manager.delete(data["job_id"], data["confirmed"])
    elif action == "template_save":
        manager.editable()
        config = manager.configuration()
        if "job_id" in data:
            config["jobs"] = [j for j in config["jobs"] if j["id"] == data["job_id"]]
        result = {"id": await workspace.templates.save(data["name"], config, "job_id" in data)}
    elif action == "template_rename":
        await workspace.templates.rename(data["template_id"], data["name"])
    elif action == "template_delete":
        await workspace.templates.delete(data["template_id"])
    elif action == "application_preview":
        if data["source"] == "history":
            config = manager.history.get(data["snapshot_id"])
            if not config.get("restorable", True):
                raise HomeAssistantError("Snapshot contains redacted secrets; restore unavailable")
        else:
            config = source_configuration(workspace, data)
        result = await workspace.prepare(data["entry_id"], config, data["source"] == "history", data["mapping"],
                                         "rollback" if data["source"] == "history" else data["source"])
    elif action == "application_stage":
        result = {"count": await workspace.stage(data["application_id"])}
    elif action == "history_diff":
        before = manager.history.get(data["snapshot_id"])
        after = manager.history.get(data["other_id"]) if data.get("other_id") else manager.configuration()
        result = {"changes": redact(snapshot_diff(before, after))}
    elif action == "history_delete":
        await manager.history.delete(data["snapshot_id"])
    elif action == "retention":
        await manager.history.retention(data["limit"])
    elif action == "diagnostics":
        result = {"schema_version": 1, "device": manager.view(), "history_count": len(manager.history.items)}
    elif action == "bulk_preview":
        config = source_configuration(workspace, data) if data["operation"] == "template" else None
        result = await workspace.bulk_preview(data["entry_ids"], data["operation"], config, data["match"], data["mapping"])
    elif action == "bulk_start":
        batch = workspace.batches.get(data["batch_id"])
        if not batch or batch["status"] != "preview":
            raise HomeAssistantError("Bulk preview expired or already started")
        batch["status"] = "queued"
        async def run():
            outcome = await workspace.bulk_execute(data["batch_id"], True)
            for record in outcome["devices"]:
                persistent_notification.async_create(workspace.hass, f"Bulk result: {record['status']}. {record.get('error', '')}",
                                                     title="Shelly Schedule Manager", notification_id=f"{DOMAIN}_{record['entry_id']}_result")
        workspace.hass.async_create_task(run())
        result = {"batch_id": data["batch_id"]}
    workspace.notify()
    return result


def register(hass, workspace):
    def report(action, data, result=None, failed=False):
        if action in ("status", "preview", "diagnostics", "history_diff", "application_preview", "bulk_preview", "bulk_start"):
            return
        entry_id = data.get("entry_id", "workspace")
        message = f"{action}: {'failed; inspect the action error and Load after partial writes' if failed else 'completed'}."
        if action in ("create", "edit", "duplicate", "delete", "restore", "application_stage") and not failed:
            message += " Changes are staged locally; preview and confirm Save to apply to Shelly."
        if action == "test_connection" and result:
            message = f"Last manual test: {result.get('status')}. {result.get('last_error', '')}"
        persistent_notification.async_create(hass, message, title="Shelly Schedule Manager",
                                             notification_id=f"{DOMAIN}_{entry_id}_result")

    async def handle_service(call):
        try:
            result = await dispatch(workspace, call.data["action"], call.data.get("data", {}))
            report(call.data["action"], call.data.get("data", {}), result)
            return result
        except Exception:
            # Expected messages are sanitized at the RPC boundary; never log request data.
            persistent_notification.async_create(hass, "Operation failed. Inspect the action error; partial writes may have applied. Load before retrying.", title="Shelly Schedule Manager", notification_id=f"{DOMAIN}_service_result")
            raise

    async_register_admin_service(hass, DOMAIN, "manage", handle_service,
                                 vol.Schema({vol.Required("action"): vol.In(list(SCHEMAS)), vol.Optional("data", default={}): dict}),
                                 supports_response=SupportsResponse.OPTIONAL)

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/manage", vol.Required("action"): vol.In(list(SCHEMAS)), vol.Optional("data", default={}): dict})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def manage(hass, connection, msg):
        try:
            result = await dispatch(workspace, msg["action"], msg.get("data", {}))
            report(msg["action"], msg.get("data", {}), result)
            connection.send_result(msg["id"], result)
        except (HomeAssistantError, ShellyAPIError, KeyError, ValueError, TypeError) as exc:
            report(msg["action"], msg.get("data", {}), failed=True)
            connection.send_error(msg["id"], "manager_error", str(exc))

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
    @websocket_api.require_admin
    @callback
    def subscribe(hass, connection, msg):
        @callback
        def send():
            connection.send_event(msg["id"], workspace.view())
        connection.subscriptions[msg["id"]] = workspace.subscribe(send)
        connection.send_result(msg["id"])
        send()

    websocket_api.async_register_command(hass, manage)
    websocket_api.async_register_command(hass, subscribe)
