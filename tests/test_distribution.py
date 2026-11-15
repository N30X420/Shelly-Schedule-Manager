"""Validate local HACS metadata, module distribution and integration JSON/YAML."""
import ast
import json
from pathlib import Path
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components/shelly_schedule_manager"


class DistributionTests(unittest.TestCase):
    def test_device_schedule_inventory_metadata(self):
        source = ast.parse((INTEGRATION / "button.py").read_text(encoding="utf-8"))
        button = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == "ScheduleButton")
        getter = next(node for node in button.body if isinstance(node, ast.FunctionDef) and node.name == "extra_state_attributes")
        getter.decorator_list = []
        namespace = {}
        exec(compile(ast.Module(body=[getter], type_ignores=[]), "button.py", "exec"), namespace)
        manager = SimpleNamespace(jobs={9: None, -1: None, 2: None, 0: None})
        entity = SimpleNamespace(manager=manager)
        self.assertEqual({"schedule_job_ids": [0, 2, 9], "schedule_count": 3}, namespace["extra_state_attributes"](entity))
        manager.jobs.clear()
        self.assertEqual({"schedule_job_ids": [], "schedule_count": 0}, namespace["extra_state_attributes"](entity))

    def test_manifest_and_hacs_metadata(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        hacs = json.loads((ROOT / "hacs.json").read_text())
        self.assertEqual("shelly_schedule_manager", manifest["domain"])
        self.assertEqual("0.7.0", manifest["version"])
        self.assertEqual(["domain", "name"] + sorted(set(manifest) - {"domain", "name"}), list(manifest))
        self.assertTrue(manifest["config_flow"])
        self.assertIn("websocket_api", manifest["dependencies"])
        self.assertTrue(hacs["render_readme"])

    def test_translations_and_python_syntax(self):
        reference = json.loads((INTEGRATION / "strings.json").read_text())
        def keys(value):
            return {key: keys(item) if isinstance(item, dict) else None for key, item in value.items()}
        for path in (INTEGRATION / "translations").glob("*.json"):
            self.assertEqual(keys(reference), keys(json.loads(path.read_text(encoding="utf-8"))))
        for path in INTEGRATION.glob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def test_all_frontend_dependencies_are_bundled(self):
        assets = INTEGRATION / "www"
        setup = (INTEGRATION / "__init__.py").read_text()
        for name in ("shelly-schedule-card.js", "shelly-schedule-card-nl.js", "manager-panel.js", "timeline.js"):
            self.assertTrue((assets / name).is_file())
            self.assertIn('"' + name + '"', setup)
        self.assertFalse((ROOT / "shelly-schedule-card.js").exists())

    def test_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("Install PyYAML to validate workflow and action descriptions")
        workflow = yaml.safe_load((ROOT / ".github/workflows/validate.yml").read_text())
        self.assertEqual({"tests", "hacs", "hassfest"}, set(workflow["jobs"]))
        services = yaml.safe_load((INTEGRATION / "services.yaml").read_text())
        self.assertIn("manage", services)
