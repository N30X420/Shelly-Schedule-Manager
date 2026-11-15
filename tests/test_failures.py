"""Write recovery, transport redaction and verification failure scenarios."""
from copy import deepcopy
from unittest.mock import patch
import unittest

from test_manager import FakeClient, FakeHass, MemoryStore, raw
from custom_components.shelly_schedule_manager.api import ShellyAPIError, ShellyClient
from custom_components.shelly_schedule_manager.manager import ScheduleManager
from custom_components.shelly_schedule_manager.security import redact


class FailureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = ScheduleManager(FakeHass(), FakeClient())
        self.manager.state_store = MemoryStore()
        self.manager.name_store = MemoryStore()
        await self.manager.load()

    async def test_created_id_survives_later_create_failure(self):
        await self.manager.duplicate(1, "First")
        await self.manager.duplicate(1, "Second")
        original = self.manager.client.call
        creates = 0
        def fail_second(method, params=None):
            nonlocal creates
            if method == "Schedule.Create":
                creates += 1
                if creates == 2:
                    raise ShellyAPIError("Timeout", "timeout")
            return original(method, params)
        self.manager.client.call = fail_second
        preview = await self.manager.preview()
        with self.assertRaisesRegex(Exception, "Partial save: 1/2"):
            await self.manager.save(preview["review_id"])
        self.assertIn(10, self.manager.jobs)
        self.assertFalse(self.manager.jobs[10].dirty)
        self.assertEqual("Second", self.manager.job_names[10])
        self.assertTrue(self.manager.recovery_required)

    async def test_readback_mismatch_stays_dirty(self):
        original = self.manager.client.call
        def ignore_update(method, params=None):
            if method == "Schedule.Update":
                return {"rev": 1}
            return original(method, params)
        self.manager.client.call = ignore_update
        await self.manager.edit(1, {"enabled": False})
        with self.assertRaisesRegex(Exception, "Verification mismatch"):
            await self.manager.save()
        self.assertTrue(self.manager.jobs[1].dirty)

    async def test_readback_failure_does_not_retry_create(self):
        original = self.manager.client.call
        def fail_readback(method, params=None):
            result = original(method, params)
            if method == "Schedule.Create":
                self.manager.client.fail = "Schedule.List"
            return result
        self.manager.client.call = fail_readback
        await self.manager.duplicate(1)
        preview = await self.manager.preview()
        with self.assertRaisesRegex(Exception, "read-back failed"):
            await self.manager.save(preview["review_id"])
        self.assertIn(10, self.manager.jobs)
        self.assertTrue(self.manager.jobs[10].uncertain)
        self.assertEqual(10, self.manager.state_store.value["journal"]["assigned_id"])

    async def test_initial_load_keeps_recovery_marker(self):
        self.manager.journal = {"operation": "create", "temporary_id": -1}
        self.manager.recovery_required = True
        await self.manager.load(initial=True)
        self.assertTrue(self.manager.recovery_required)
        with self.assertRaisesRegex(Exception, "Uncertain"):
            await self.manager.save()
        await self.manager.load()
        self.assertFalse(self.manager.recovery_required)

    async def test_backup_advanced_and_restore_staged(self):
        self.manager.backup_store = MemoryStore()
        self.manager.client.jobs[1]["timespec"] = "@sunset"
        await self.manager.load()
        await self.manager.make_backup()
        await self.manager.set_job_name(1, "Existing name")
        await self.manager.edit(1, {"enabled": False})
        before = deepcopy(self.manager.client.jobs)
        await self.manager.stage_restore()
        self.assertEqual(before, self.manager.client.jobs)
        self.assertEqual("@sunset", self.manager.jobs[1].timespec)
        self.assertEqual("Existing name", self.manager.job_names[1])

    async def test_recursive_secret_redaction(self):
        value = {"password": "one", "calls": [{"params": {"Authorization": "two", "nested": {"access_token": "three"}, "url": "http://user:pass@host/?token=four"}}]}
        clean = str(redact(value))
        for secret in ("one", "two", "three", "four", "user:pass"):
            self.assertNotIn(secret, clean)

    async def test_delete_needs_confirmation_and_unsaved_creation_is_cancelled(self):
        with self.assertRaises(Exception):
            await self.manager.delete(1)
        new_id = await self.manager.duplicate(1)
        await self.manager.delete(new_id, True)
        self.assertEqual([], self.manager.pending())

    async def test_created_job_can_reuse_a_verified_deleted_id(self):
        await self.manager.duplicate(1, "Replacement")
        await self.manager.delete(1, True)
        self.manager.client.next_id = 1
        preview = await self.manager.preview()
        self.assertEqual(2, await self.manager.save(preview["review_id"]))
        self.assertEqual({1}, set(self.manager.jobs))
        self.assertEqual("Replacement", self.manager.job_names[1])
        self.assertFalse(self.manager.jobs[1].dirty)
        self.assertFalse(self.manager.recovery_required)


class TransportTests(unittest.TestCase):
    def test_timeout_and_http_auth_errors_are_sanitized(self):
        import requests
        client = ShellyClient("192.0.2.1", "admin", "DEVICE_PASSWORD")
        for error, kind in ((requests.Timeout("password=DO_NOT_LOG"), "timeout"),
                            (requests.HTTPError("token=DO_NOT_LOG"), "authentication_failed")):
            if kind == "authentication_failed":
                error.response = type("Response", (), {"status_code": 401})()
            with patch.object(requests, "Session", create=True) as session:
                session.return_value.__enter__.return_value.post.side_effect = error
                with self.assertRaises(ShellyAPIError) as raised:
                    client.call("Schedule.List")
                self.assertEqual(kind, raised.exception.kind)
                self.assertNotIn("DO_NOT_LOG", str(raised.exception))
                self.assertNotIn("DEVICE_PASSWORD", str(raised.exception))
