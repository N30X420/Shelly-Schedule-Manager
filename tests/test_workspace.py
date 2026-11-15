"""Controlled multi-device writes, per-device failures and diagnostics."""
import asyncio
import unittest

from test_manager import FakeClient, FakeHass, MemoryStore, raw
from custom_components.shelly_schedule_manager.api import ShellyAPIError
from custom_components.shelly_schedule_manager.manager import ScheduleManager
from custom_components.shelly_schedule_manager.storage import History, Templates
from custom_components.shelly_schedule_manager.workspace import Workspace


class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.workspace = Workspace(FakeHass(), Templates(MemoryStore()))
        for entry_id in ("one", "two", "three"):
            manager = ScheduleManager(FakeHass(), FakeClient())
            manager.client.identity = f"shelly-{entry_id}"
            manager.entry_id = entry_id
            manager.history = History(MemoryStore(), entry_id)
            await manager.load()
            self.workspace.managers[entry_id] = manager

    async def test_multiple_successful_devices(self):
        batch = await self.workspace.bulk_preview(["one", "two"], "disable")
        self.assertEqual({"pending"}, {r["status"] for r in batch["devices"]})
        self.assertTrue(self.workspace.manager("one").client.jobs[1]["enable"])
        result = await self.workspace.bulk_execute(batch["id"], True)
        self.assertEqual("success", result["status"])
        for entry_id in ("one", "two"):
            manager = self.workspace.manager(entry_id)
            self.assertFalse(manager.client.jobs[1]["enable"])
            self.assertEqual("bulk", manager.history.list()[0]["source"])

    async def test_partial_failure_and_conflict(self):
        batch = await self.workspace.bulk_preview(["one", "two", "three"], "disable")
        self.workspace.manager("two").client.fail = "Schedule.Update"
        self.workspace.manager("three").client.jobs[1]["timespec"] = "0 0 5 * * *"
        result = await self.workspace.bulk_execute(batch["id"], True)
        self.assertEqual("partial_or_failed", result["status"])
        self.assertEqual(["success", "failed", "conflict"], [r["status"] for r in result["devices"]])

    async def test_authentication_timeout_skipped_and_confirmation(self):
        manager = self.workspace.manager("one")
        original = manager.client.call
        def auth_failure(method, params=None):
            if method == "Shelly.GetDeviceInfo":
                raise ShellyAPIError("Authentication failed", "authentication_failed")
            return original(method, params)
        manager.client.call = auth_failure
        self.workspace.manager("two").client.fail = "Schedule.List"
        batch = await self.workspace.bulk_preview(["one", "two", "three"], "disable", match="missing")
        self.assertTrue(all(r["status"] == "skipped" for r in batch["devices"]))
        batch = await self.workspace.bulk_preview(["one", "two"], "disable")
        self.assertEqual(["failed", "failed"], [r["status"] for r in batch["devices"]])
        with self.assertRaises(Exception):
            await self.workspace.bulk_execute(batch["id"], False)

    async def test_clone_bulk_uses_new_ids(self):
        config = self.workspace.manager("one").configuration()
        batch = await self.workspace.bulk_preview(["two", "three"], "template", config)
        result = await self.workspace.bulk_execute(batch["id"], True)
        self.assertEqual("success", result["status"])
        self.assertEqual({1, 10}, set(self.workspace.manager("two").client.jobs))

    async def test_diagnostics_manual_and_secret_free(self):
        manager = self.workspace.manager("one")
        manager.client.calls.clear()
        manager.view()
        self.assertEqual([], manager.client.calls)
        result = await manager.test_connection()
        self.assertEqual("connected", result["status"])
        self.assertEqual("Europe/Amsterdam", result["timezone"])
        self.assertNotIn("NEVER EXPORT", str(result))
        self.assertIn("checked_at", result)
        self.assertIn("response_ms", result)
        self.assertFalse(any(m.startswith("Schedule.") and m != "Schedule.List" for m, _ in manager.client.calls))

    async def test_diagnostics_timeout_auth_rpc_and_identity(self):
        manager = self.workspace.manager("one")
        for kind in ("timeout", "authentication_failed", "network_error", "rpc_error"):
            def fail(method, params=None):
                raise ShellyAPIError("Sanitized failure", kind)
            original = manager.client.call
            manager.client.call = fail
            self.assertEqual(kind, (await manager.test_connection())["status"])
            manager.client.call = original
        await manager.test_connection()
        manager.client.identity = "replacement-device"
        self.assertEqual("unsupported_device", (await manager.test_connection())["status"])

    async def test_missing_optional_metadata(self):
        manager = self.workspace.manager("one")
        original = manager.client.call
        def minimal(method, params=None):
            result = original(method, params)
            if method == "Shelly.GetDeviceInfo":
                return {"id": "shelly-test", "gen": 3}
            if method == "Sys.GetConfig":
                return {}
            return result
        manager.client.call = minimal
        result = await manager.test_connection()
        self.assertEqual("connected", result["status"])
        self.assertIsNone(result.get("timezone"))

    async def test_preview_is_immutable_and_stale_protected(self):
        config = {"jobs": [raw()]}
        application = await self.workspace.prepare("one", config)
        config["jobs"].clear()
        await self.workspace.stage(application["application_id"])
        self.assertEqual(2, len(self.workspace.manager("one").jobs))
        application = await self.workspace.prepare("two", {"jobs": [raw()]})
        await self.workspace.manager("two").edit(1, {"enabled": False})
        with self.assertRaisesRegex(Exception, "stale"):
            await self.workspace.stage(application["application_id"])

    async def test_concurrency_is_bounded_and_disconnected_ui_isolated(self):
        class ConcurrentHass(FakeHass):
            active = 0
            maximum = 0
            async def async_add_executor_job(self, func, *args):
                self.active += 1
                self.maximum = max(self.maximum, self.active)
                try:
                    await asyncio.sleep(0)
                    return func(*args)
                finally:
                    self.active -= 1
        hass = ConcurrentHass()
        for manager in self.workspace.managers.values():
            manager.hass = hass
        def disconnected():
            raise RuntimeError("Connection closed")
        self.workspace.subscribe(disconnected)
        batch = await self.workspace.bulk_preview(["one", "two", "three"], "disable")
        result = await self.workspace.bulk_execute(batch["id"], True)
        self.assertEqual("success", result["status"])
        self.assertEqual(2, hass.maximum)

    async def test_same_physical_device_cannot_execute_twice_in_bulk(self):
        self.workspace.manager("two").client.identity = self.workspace.manager("one").client.identity
        batch = await self.workspace.bulk_preview(["one", "two"], "disable")
        self.assertEqual(["conflict", "conflict"], [r["status"] for r in batch["devices"]])
        result = await self.workspace.bulk_execute(batch["id"], True)
        self.assertEqual("partial_or_failed", result["status"])
        self.assertTrue(self.workspace.manager("one").client.jobs[1]["enable"])
