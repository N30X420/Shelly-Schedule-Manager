"""Existing Switch.Set output edits remain staged, validated and verified."""
from copy import deepcopy
import unittest

from test_manager import FakeClient, FakeHass, MemoryStore, raw
from custom_components.shelly_schedule_manager.manager import ScheduleManager
from homeassistant.exceptions import HomeAssistantError


class OutputTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = FakeClient()
        original = self.client.call
        self.allow_create = True
        def two_outputs(method, params=None):
            result = original(method, params)
            if method == "Shelly.GetStatus":
                result["switch:1"] = {}
            if method == "Shelly.ListMethods" and not self.allow_create:
                result["methods"].remove("Schedule.Create")
            return result
        self.client.call = two_outputs
        self.manager = ScheduleManager(FakeHass(), self.client)
        self.manager.name_store = MemoryStore()
        self.manager.state_store = MemoryStore()
        await self.manager.load()
        self.client.calls.clear()

    async def test_output_edit_stages_and_updates_without_create_permission(self):
        self.client.jobs[1]["calls"][0]["params"].update(toggle_after=60, tag="schedule")
        await self.manager.load()
        self.client.calls.clear()
        self.allow_create = False
        await self.manager.edit(1, {"switch_id": 1, "on": False})
        self.assertEqual([], self.client.calls)
        self.assertEqual(0, self.client.jobs[1]["calls"][0]["params"]["id"])
        self.assertEqual({"id": 1, "on": False, "toggle_after": 60, "tag": "schedule"}, self.manager.jobs[1].calls[0]["params"])
        with self.assertRaisesRegex(HomeAssistantError, "Preview and confirm"):
            await self.manager.save()
        preview = await self.manager.preview()
        self.assertEqual(0, preview["changes"][0]["before"]["calls"][0]["params"]["id"])
        self.assertEqual(1, preview["changes"][0]["after"]["calls"][0]["params"]["id"])
        self.assertEqual(1, await self.manager.save(preview["review_id"]))
        self.assertEqual(self.manager.jobs[1].calls, self.client.jobs[1]["calls"])
        self.assertEqual(raw()["timespec"], self.client.jobs[1]["timespec"])
        self.assertFalse(self.manager.jobs[1].dirty)
        self.assertFalse(any(method == "Schedule.Create" for method, _ in self.client.calls))

    async def test_invalid_output_types_leave_job_unchanged(self):
        original = self.manager.configuration()
        for changes in ({"switch_id": True}, {"switch_id": -1}, {"switch_id": "1"}, {"switch_id": None}, {"on": 1}, {"on": "false"}, {"on": None}):
            with self.assertRaises(HomeAssistantError):
                await self.manager.edit(1, changes)
            self.assertEqual(original, self.manager.configuration())
        self.assertEqual([], self.client.calls)

    async def test_missing_output_is_rejected_before_save(self):
        await self.manager.edit(1, {"switch_id": 99})
        with self.assertRaisesRegex(HomeAssistantError, "switch component"):
            await self.manager.preview()
        self.assertFalse(any(method == "Schedule.Update" for method, _ in self.client.calls))

    async def test_external_action_change_conflicts(self):
        await self.manager.edit(1, {"on": False})
        preview = await self.manager.preview()
        self.client.jobs[1]["calls"][0]["params"]["id"] = 1
        with self.assertRaisesRegex(HomeAssistantError, "Conflict"):
            await self.manager.save(preview["review_id"])
        self.assertFalse(any(method == "Schedule.Update" for method, _ in self.client.calls))

    async def test_custom_and_multiple_actions_are_preserved(self):
        for calls in ([{"method": "Custom.RPC", "params": {"id": 0}}], raw()["calls"] + [{"method": "Switch.Set", "params": {"id": 1, "on": True}}]):
            self.client.jobs[1]["calls"] = deepcopy(calls)
            await self.manager.load()
            with self.assertRaisesRegex(HomeAssistantError, "single Switch.Set"):
                await self.manager.edit(1, {"switch_id": 1, "on": False})
            self.assertEqual(calls, self.manager.jobs[1].calls)

    async def test_staged_new_job_output_can_be_edited(self):
        key = await self.manager.create("New", "08:00:00", "0,1,2,3,4,5,6", 0, True)
        await self.manager.edit(key, {"switch_id": 1, "on": False})
        self.assertEqual("create", self.manager.jobs[key].operation)
        self.assertEqual(1, len(self.client.jobs))
        preview = await self.manager.preview()
        await self.manager.save(preview["review_id"])
        self.assertEqual({"id": 1, "on": False}, self.client.jobs[10]["calls"][0]["params"])

    async def test_output_mismatch_does_not_mark_clean(self):
        original = self.client.call
        def ignore_update(method, params=None):
            return {} if method == "Schedule.Update" else original(method, params)
        self.client.call = ignore_update
        await self.manager.edit(1, {"switch_id": 1})
        preview = await self.manager.preview()
        with self.assertRaisesRegex(HomeAssistantError, "Verification mismatch"):
            await self.manager.save(preview["review_id"])
        self.assertTrue(self.manager.jobs[1].dirty)
