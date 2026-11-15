"""Exercise actual action validation and dispatch with mocked HA registration APIs."""
import asyncio
import sys
from types import ModuleType, SimpleNamespace
import unittest

from test_manager import FakeClient, FakeHass, MemoryStore

try:
    import voluptuous as vol
except ImportError:
    raise unittest.SkipTest("Install voluptuous to run Home Assistant action-schema tests")

from custom_components.shelly_schedule_manager.manager import ScheduleManager
from custom_components.shelly_schedule_manager.storage import History, Templates
from custom_components.shelly_schedule_manager.workspace import Workspace
from homeassistant.exceptions import HomeAssistantError

registered = {}
notifications = []
def module(name, **attrs):
    value = ModuleType(name)
    value.__dict__.update(attrs)
    sys.modules[name] = value
    return value

def websocket_command(schema):
    def decorate(func):
        func.schema = vol.Schema(dict(schema, **{"id": int}))
        return func
    return decorate

def require_admin(func):
    def decorate(hass, connection, msg):
        if not connection.user.is_admin:
            raise HomeAssistantError("Administrator required")
        return func(hass, connection, msg)
    return decorate

components = module("homeassistant.components")
components.persistent_notification = module("homeassistant.components.persistent_notification", async_create=lambda *args, **kwargs: notifications.append((args, kwargs)))
components.websocket_api = module("homeassistant.components.websocket_api", websocket_command=websocket_command,
                                  require_admin=require_admin, async_response=lambda f: f,
                                  async_register_command=lambda hass, func: registered.setdefault(str(func.schema.schema), func))
module("homeassistant.core", SupportsResponse=SimpleNamespace(OPTIONAL="optional"), callback=lambda f: f)
module("homeassistant.helpers")
module("homeassistant.helpers.service", async_register_admin_service=lambda hass, domain, name, handler, schema, **kwargs: registered.update(service=(handler, schema, kwargs)))

from custom_components.shelly_schedule_manager.services import dispatch, register


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.workspace = Workspace(FakeHass(), Templates(MemoryStore()))
        self.manager = ScheduleManager(FakeHass(), FakeClient())
        self.manager.entry_id = "entry"
        self.manager.history = History(MemoryStore(), "entry")
        await self.manager.load()
        self.workspace.managers["entry"] = self.manager

    async def test_dispatch_create_preview_confirm_save(self):
        created = await dispatch(self.workspace, "create", {"entry_id": "entry", "name": "Office", "time": "09:00:00", "weekdays": "1", "switch_id": 0, "on": True, "enabled": True})
        self.assertLess(created["id"], 0)
        preview = await dispatch(self.workspace, "preview", {"entry_id": "entry"})
        with self.assertRaises(HomeAssistantError):
            await dispatch(self.workspace, "save", {"entry_id": "entry", "review_id": preview["review_id"], "confirmed": False})
        result = await dispatch(self.workspace, "save", {"entry_id": "entry", "review_id": preview["review_id"], "confirmed": True})
        self.assertEqual(1, result["verified"])

    async def test_invalid_entry_and_extra_parameters(self):
        for action, data in (("load", {"entry_id": "unknown"}), ("create", {"entry_id": "entry", "host": "arbitrary"}), ("status", {"password": "SHOULD_NOT_ACCEPT"}), ("delete", {"entry_id": "entry", "job_id": True, "confirmed": True})):
            with self.assertRaises(HomeAssistantError):
                await dispatch(self.workspace, action, data)

    async def test_templates_dispatch_history_and_diagnostics(self):
        saved = await dispatch(self.workspace, "template_save", {"entry_id": "entry", "name": "Office", "job_id": 1})
        proposal = await dispatch(self.workspace, "application_preview", {"entry_id": "entry", "source": "template", "template_id": saved["id"]})
        await dispatch(self.workspace, "application_stage", {"application_id": proposal["application_id"], "confirmed": True})
        self.assertEqual(2, len(self.manager.jobs))
        await dispatch(self.workspace, "retention", {"entry_id": "entry", "limit": 5})
        self.assertEqual(5, self.manager.history.limit)
        export = await dispatch(self.workspace, "diagnostics", {"entry_id": "entry"})
        self.assertNotIn("auth", export)

    async def test_admin_registration_and_read_only_subscription(self):
        registered.clear()
        register(self.workspace.hass, self.workspace)
        self.assertEqual("optional", registered["service"][2]["supports_response"])
        handlers = [value for key, value in registered.items() if key != "service"]
        denied = SimpleNamespace(user=SimpleNamespace(is_admin=False))
        for handler in handlers:
            with self.assertRaisesRegex(HomeAssistantError, "Administrator"):
                handler(self.workspace.hass, denied, {"id": 1})
        subscription = next(h for h in handlers if "subscribe" in str(h.schema.schema))
        results, events = [], []
        connection = SimpleNamespace(user=SimpleNamespace(is_admin=True), subscriptions={},
                                     send_result=lambda *args: results.append(args), send_event=lambda *args: events.append(args))
        self.manager.client.calls.clear()
        subscription(self.workspace.hass, connection, {"id": 3})
        self.assertEqual([], self.manager.client.calls)
        self.assertEqual(1, len(events))
        connection.subscriptions[3]()
        self.workspace.notify()
        self.assertEqual(1, len(events))
