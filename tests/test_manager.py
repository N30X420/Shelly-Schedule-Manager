"""Offline regression tests. No Home Assistant install or physical Shelly required."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "custom_components.shelly_schedule_manager"
package = ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "custom_components/shelly_schedule_manager")]
sys.modules.setdefault(PACKAGE, package)
if importlib.util.find_spec("homeassistant") is None:
    for name in ("homeassistant", "homeassistant.exceptions"):
        sys.modules[name] = ModuleType(name)
    class HomeAssistantError(Exception):
        pass
    sys.modules["homeassistant.exceptions"].HomeAssistantError = HomeAssistantError

if importlib.util.find_spec("requests") is None:
    # Transport is mocked offline; Home Assistant supplies requests at runtime.
    requests = ModuleType("requests")
    requests.RequestException = type("RequestException", (Exception,), {})
    requests.Timeout = type("Timeout", (requests.RequestException,), {})
    requests.HTTPError = type("HTTPError", (requests.RequestException,), {})
    requests.auth = ModuleType("requests.auth")
    requests.auth.HTTPDigestAuth = lambda username, password: (username, password)
    sys.modules["requests"] = requests
    sys.modules["requests.auth"] = requests.auth

from custom_components.shelly_schedule_manager.api import ShellyAPIError
from custom_components.shelly_schedule_manager.manager import ScheduleManager
from custom_components.shelly_schedule_manager.model import parse_job, snapshot_diff
from homeassistant.exceptions import HomeAssistantError


def raw(job_id=1, timespec="0 0 8 * * 1,2,3,4,5", on=True):
    return {"id": job_id, "timespec": timespec, "enable": True,
            "calls": [{"method": "Switch.Set", "params": {"id": 0, "on": on}}]}


class MemoryStore:
    def __init__(self, value=None):
        self.value = deepcopy(value)

    async def async_load(self):
        return deepcopy(self.value)

    async def async_save(self, value):
        self.value = deepcopy(value)


class FakeHass:
    async def async_add_executor_job(self, func, *args):
        return func(*args)


class FakeClient:
    host = "192.0.2.1"

    def __init__(self, jobs=None):
        self.jobs = {j["id"]: deepcopy(j) for j in (jobs if jobs is not None else [raw()])}
        self.calls = []
        self.fail = None
        self.create_mode = None
        self.next_id = 10
        self.identity = "shelly-test"

    def call(self, method, params=None):
        self.calls.append((method, deepcopy(params)))
        if method == self.fail:
            raise ShellyAPIError("Simulated timeout", "timeout")
        if method == "Schedule.List":
            return {"jobs": deepcopy(list(self.jobs.values())), "rev": len(self.calls)}
        if method == "Shelly.GetDeviceInfo":
            return {"id": self.identity, "gen": 3, "model": "test", "ver": "1.0"}
        if method == "Shelly.ListMethods":
            return {"methods": ["Schedule.List", "Schedule.Create", "Schedule.Update", "Schedule.Delete", "Switch.Set", "Shelly.GetStatus", "Sys.GetConfig"]}
        if method == "Shelly.GetStatus":
            return {"switch:0": {}, "sys": {"time": "12:00"}}
        if method == "Sys.GetConfig":
            return {"location": {"tz": "Europe/Amsterdam"}, "password": "NEVER EXPORT"}
        if method == "Schedule.Create":
            assigned = self.next_id
            self.next_id += 1
            self.jobs[assigned] = dict(deepcopy(params), id=assigned)
            if self.create_mode == "timeout":
                raise ShellyAPIError("Simulated timeout", "timeout")
            if self.create_mode == "unknown":
                return {}
            return {"id": assigned}
        if method == "Schedule.Update":
            self.jobs[params["id"]].update(deepcopy(params))
            return {"rev": 1}
        if method == "Schedule.Delete":
            self.jobs.pop(params["id"])
            return {"rev": 1}
        raise ShellyAPIError("Unsupported method")


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = FakeClient()
        self.manager = ScheduleManager(FakeHass(), self.client)
        self.manager.name_store = MemoryStore()
        self.manager.state_store = MemoryStore()
        self.manager.backup_store = MemoryStore()
        await self.manager.load()
        self.client.calls.clear()

    async def test_edit_stages_and_verified_save(self):
        await self.manager.edit(1, {"time": "09:00:00", "enabled": False})
        self.assertEqual([], self.client.calls)
        self.assertEqual(1, await self.manager.save())
        self.assertFalse(self.manager.jobs[1].dirty)
        self.assertEqual("0 0 9 * * 1,2,3,4,5", self.client.jobs[1]["timespec"])

    async def test_create_new_id_names_and_no_duplicate_retry(self):
        new_id = await self.manager.create("Office", "09:30:00", "1,2", 0, True)
        self.assertLess(new_id, 0)
        self.assertEqual([], self.client.calls)
        preview = await self.manager.preview()
        self.assertEqual(1, await self.manager.save(preview["review_id"]))
        self.assertIn(10, self.manager.jobs)
        self.assertEqual("Office", self.manager.job_names[10])
        self.assertEqual(0, await self.manager.save())
        self.assertEqual(1, sum(m == "Schedule.Create" for m, _ in self.client.calls))

    async def test_duplicate_delete_and_order(self):
        await self.manager.duplicate(1, "Copy")
        await self.manager.delete(1, True)
        preview = await self.manager.preview()
        await self.manager.save(preview["review_id"])
        writes = [m for m, _ in self.client.calls if m in ("Schedule.Create", "Schedule.Delete")]
        self.assertEqual(["Schedule.Delete", "Schedule.Create"], writes)
        self.assertNotIn(1, self.manager.jobs)

    async def test_conflict_writes_nothing(self):
        await self.manager.edit(1, {"enabled": False})
        self.client.jobs[1]["timespec"] = "0 0 10 * * *"
        with self.assertRaisesRegex(HomeAssistantError, "Conflict"):
            await self.manager.save()
        self.assertFalse(any(m == "Schedule.Update" for m, _ in self.client.calls))

    async def test_unknown_creation_requires_load(self):
        for mode in ("timeout", "unknown"):
            await self.manager.load()
            await self.manager.create("New", "12:00:00", "0", 0, False)
            preview = await self.manager.preview()
            self.client.create_mode = mode
            with self.assertRaisesRegex(HomeAssistantError, "Partial save"):
                await self.manager.save(preview["review_id"])
            self.assertTrue(self.manager.recovery_required)
            self.assertIsNotNone(self.manager.state_store.value["journal"])
            count = len(self.client.calls)
            with self.assertRaises(HomeAssistantError):
                await self.manager.save()
            self.assertEqual(count, len(self.client.calls))

    async def test_capacity_and_unsupported_channel(self):
        self.manager.capabilities.capacity = 1
        with self.assertRaisesRegex(HomeAssistantError, "capacity"):
            await self.manager.duplicate(1)
        self.manager.capabilities.capacity = 20
        await self.manager.create("Other", "10:00:00", "1", 99, True)
        with self.assertRaisesRegex(HomeAssistantError, "switch"):
            await self.manager.preview()

    async def test_advanced_jobs_preserved(self):
        self.client.jobs[1]["timespec"] = "@sunset+30m"
        self.client.jobs[1]["calls"].append({"method": "Custom.RPC", "params": {"value": 5}})
        await self.manager.load()
        self.assertIsNone(self.manager.jobs[1].local_time)
        await self.manager.edit(1, {"enabled": False})
        await self.manager.save()
        self.assertEqual("@sunset+30m", self.client.jobs[1]["timespec"])
        self.assertEqual(2, len(self.client.jobs[1]["calls"]))

    async def test_stale_preview(self):
        await self.manager.duplicate(1)
        preview = await self.manager.preview()
        await self.manager.edit(1, {"enabled": False})
        with self.assertRaisesRegex(HomeAssistantError, "stale"):
            await self.manager.save(preview["review_id"])


if __name__ == "__main__":
    unittest.main()
