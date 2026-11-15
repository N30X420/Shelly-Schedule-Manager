"""Template, clone, history and legacy migration regression tests."""
from copy import deepcopy
import unittest

from test_manager import FakeClient, FakeHass, MemoryStore, raw
from custom_components.shelly_schedule_manager.manager import ScheduleManager
from custom_components.shelly_schedule_manager.model import snapshot_diff
from custom_components.shelly_schedule_manager.storage import History, Templates
from homeassistant.exceptions import HomeAssistantError


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.templates = Templates(MemoryStore())
        await self.templates.load()
        self.config = {"jobs": [raw()], "names": {"1": "Office"}}
        self.manager = ScheduleManager(FakeHass(), FakeClient())
        self.manager.history = History(MemoryStore(), "entry")
        await self.manager.history.load()
        await self.manager.load()

    async def test_template_lifecycle_and_persistence(self):
        key = await self.templates.save("Office Hours", self.config, True)
        await self.templates.rename(key, "Weekend")
        loaded = Templates(self.templates.store)
        await loaded.load()
        self.assertEqual("Weekend", loaded.get(key)["name"])
        self.assertEqual("job", loaded.get(key)["type"])
        await self.templates.delete(key)
        self.assertEqual([], self.templates.list())

    async def test_apply_preview_does_not_stage_or_write(self):
        key = await self.templates.save("Office Hours", self.config)
        before = self.manager.configuration()
        proposal = await self.manager.stage_configuration(self.templates.get(key), dry_run=True)
        self.assertEqual(before, self.manager.configuration())
        self.assertEqual(1, proposal["changes"])
        await self.manager.stage_configuration(self.templates.get(key))
        self.assertEqual(2, len(self.manager.jobs))
        new = next(j for j in self.manager.jobs.values() if j.id < 0)
        self.assertEqual("create", new.operation)
        self.assertEqual(raw()["calls"], self.manager.client.jobs[1]["calls"])
        self.assertFalse(any(method == "Schedule.Create" for method, _ in self.manager.client.calls))

    async def test_cross_device_channel_mapping(self):
        config = deepcopy(self.config)
        config["jobs"][0]["calls"][0]["params"]["id"] = 3
        with self.assertRaisesRegex(HomeAssistantError, "switch"):
            await self.manager.stage_configuration(config)
        self.assertEqual(1, len(self.manager.jobs))
        await self.manager.stage_configuration(config, mapping={"3": 0})
        self.assertEqual(0, self.manager.jobs[-1].calls[0]["params"]["id"])

    async def test_secret_template_rejected_snapshot_redacted(self):
        config = deepcopy(self.config)
        config["jobs"][0]["calls"][0]["params"]["password"] = "NEVER STORE"
        with self.assertRaises(HomeAssistantError):
            await self.templates.save("Secret", config)
        await self.manager.history.record({1: config["jobs"][0]}, {}, "backup")
        snapshot = self.manager.history.list()[0]
        self.assertFalse(snapshot["restorable"])
        self.assertNotIn("NEVER STORE", str(snapshot))
        with self.assertRaises(HomeAssistantError):
            await self.manager.stage_configuration(snapshot, replace=True)

    async def test_history_save_restore_and_immutable_readers(self):
        original = await self.manager.history.record(self.manager.client.jobs, {1: "Office"}, "backup")
        await self.manager.edit(1, {"time": "10:00:00"})
        await self.manager.save()
        self.assertEqual("save", self.manager.history.list()[0]["source"])
        snapshot = self.manager.history.get(original)
        await self.manager.stage_configuration(snapshot, replace=True, source="rollback")
        self.assertEqual("0 0 10 * * 1,2,3,4,5", self.manager.client.jobs[1]["timespec"])
        preview = await self.manager.preview()
        await self.manager.save(preview["review_id"])
        self.assertEqual(raw()["timespec"], self.manager.client.jobs[1]["timespec"])
        self.assertEqual("rollback", self.manager.history.list()[0]["source"])
        snapshot["jobs"][0]["timespec"] = "changed outside history"
        self.assertEqual(raw()["timespec"], self.manager.history.get(original)["jobs"][0]["timespec"])

    async def test_rollback_creates_and_deletes(self):
        snapshot = {"jobs": [raw(9)], "names": {"9": "Old"}}
        await self.manager.stage_configuration(snapshot, replace=True, source="rollback")
        self.assertTrue(self.manager.jobs[1].deleted)
        self.assertNotIn(9, self.manager.jobs)
        preview = await self.manager.preview()
        await self.manager.save(preview["review_id"])
        self.assertEqual([10], list(self.manager.client.jobs))

    async def test_retention_and_migration_once(self):
        store = MemoryStore()
        legacy = {"created": "2026-01-01T00:00:00+00:00", "jobs": [raw()]}
        history = History(store, "entry")
        await history.load(legacy)
        self.assertEqual("legacy_backup", history.list()[0]["source"])
        self.assertFalse(history.list()[0]["names_recorded"])
        await history.load(legacy)
        self.assertEqual(1, len(history.items))
        reader = history.get(history.items[0]["id"])
        await history.retention(2)
        for _ in range(5):
            await history.record({1: raw()}, {}, "save")
        self.assertEqual(2, len(history.items))
        self.assertEqual(raw(), reader["jobs"][0])
        await history.delete(history.items[0]["id"])
        self.assertEqual(1, len(history.items))

    async def test_diff_all_fields(self):
        after = deepcopy(self.config)
        after["jobs"][0].update(timespec="0 30 10 * * 0", enable=False)
        after["jobs"][0]["calls"][0]["params"]["on"] = False
        after["names"]["1"] = "Changed"
        after["jobs"].append(raw(2))
        diff = snapshot_diff(self.config, after)
        self.assertEqual({"timespec", "enable", "calls", "name", "time", "weekdays"}, set(diff[0]["changes"]))
        self.assertEqual("create", diff[1]["operation"])
        self.assertEqual("delete", snapshot_diff(after, self.config)[1]["operation"])

    async def test_name_only_rollback_persists_and_load_discards(self):
        self.manager.name_store = MemoryStore()
        await self.manager.set_job_name(1, "Current")
        snapshot = dict(self.config, names={"1": "Historical"})
        await self.manager.stage_configuration(snapshot, replace=True, source="rollback")
        self.assertEqual("rename", self.manager.pending()[0]["operation"])
        self.assertEqual("Current", self.manager.name_store.value["1"])
        await self.manager.load()
        self.assertEqual("Current", self.manager.job_names[1])
        await self.manager.stage_configuration(snapshot, replace=True, source="rollback")
        preview = await self.manager.preview()
        await self.manager.save(preview["review_id"])
        self.assertEqual("Historical", self.manager.name_store.value["1"])
        self.assertEqual("rollback", self.manager.history.list()[0]["source"])
        self.assertEqual([], self.manager.pending())
