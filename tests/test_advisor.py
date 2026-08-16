"""Tests for the build advisor. Stdlib unittest; no dependencies.

These pin the three behaviours that distinguish this matcher from the
presence-only planner it generalises (see DECISIONS.md ADR-0002).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import advisor  # noqa: E402

REGISTRY = {
    "boards/mcu": {
        "id": "boards/mcu", "name": "MCU board",
        "attributes": {"capabilities": ["gpio", "sensor_read"]},
    },
    "boards/radio": {
        "id": "boards/radio", "name": "Radio board",
        "attributes": {"capabilities": ["gpio", "lora"]},
    },
    "electronic/sensor": {
        "id": "electronic/sensor", "name": "Sensor",
        "attributes": {"capabilities": ["sensor_read"]},
    },
}


class AllocationTests(unittest.TestCase):
    def test_one_part_cannot_satisfy_two_requirements(self):
        """The bug in presence-only matching: a single board filling both roles."""
        project = {
            "id": "p", "name": "Two hosts",
            "requires": [
                {"capability": "gpio", "qty": 1},
                {"capability": "lora", "qty": 1},
            ],
        }
        # One radio board has both capabilities, but only one unit exists.
        result = advisor.evaluate(project, {"boards/radio": 1}, REGISTRY)

        self.assertFalse(result["buildable"])
        gap = result["gaps"][0]
        self.assertEqual(gap["requirement"], "capability:lora")
        self.assertEqual(gap["qty_short"], 1)

    def test_quantities_are_counted_not_just_presence(self):
        project = {
            "id": "p", "name": "Two hosts",
            "requires": [{"capability": "gpio", "qty": 3}],
        }
        result = advisor.evaluate(project, {"boards/mcu": 2}, REGISTRY)

        self.assertFalse(result["buildable"])
        self.assertEqual(result["gaps"][0]["qty_short"], 1)

    def test_specific_parts_are_allocated_before_capabilities(self):
        """Otherwise a capability requirement eats the only unit of a named part."""
        project = {
            "id": "p", "name": "Sensor plus host",
            "requires": [
                {"capability": "sensor_read", "qty": 1},
                {"part_id": "electronic/sensor", "qty": 1},
            ],
        }
        owned = {"electronic/sensor": 1, "boards/mcu": 1}
        result = advisor.evaluate(project, owned, REGISTRY)

        self.assertTrue(result["buildable"], result["gaps"])

    def test_suggestions_come_from_the_registry(self):
        project = {"id": "p", "name": "Radio", "requires": [{"capability": "lora", "qty": 1}]}
        result = advisor.evaluate(project, {"boards/mcu": 1}, REGISTRY)

        suggested = [s["part_id"] for s in result["gaps"][0]["suggestions"]]
        self.assertEqual(suggested, ["boards/radio"])

    def test_owned_parts_are_not_suggested(self):
        project = {"id": "p", "name": "Radio", "requires": [{"capability": "lora", "qty": 2}]}
        result = advisor.evaluate(project, {"boards/radio": 1}, REGISTRY)

        self.assertEqual(result["gaps"][0]["qty_short"], 1)
        self.assertEqual(result["gaps"][0]["suggestions"], [])


class InventoryTests(unittest.TestCase):
    def test_unknown_part_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inv.json"
            path.write_text(json.dumps({"items": [{"part_id": "boards/nope", "qty": 1}]}))
            with self.assertRaises(SystemExit) as caught:
                advisor.load_inventory(path, REGISTRY)
            self.assertIn("not in the registry", str(caught.exception))

    def test_duplicate_lines_accumulate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inv.json"
            path.write_text(json.dumps({"items": [
                {"part_id": "boards/mcu", "qty": 2},
                {"part_id": "boards/mcu", "qty": 3},
            ]}))
            self.assertEqual(advisor.load_inventory(path, REGISTRY), {"boards/mcu": 5})


class ShippedDataTests(unittest.TestCase):
    def test_example_inventory_and_projects_resolve(self):
        parts = advisor.DEFAULT_PARTS
        if not (parts / "data").exists():
            self.skipTest("OpenPartsCore not checked out alongside this repo")
        registry = advisor.load_registry(parts)
        owned = advisor.load_inventory(advisor.DEFAULT_INVENTORY, registry)
        projects = advisor.load_projects(advisor.ROOT / "data" / "projects")
        self.assertTrue(projects)
        for project in projects:
            result = advisor.evaluate(project, owned, registry)
            self.assertIn("buildable", result)


if __name__ == "__main__":
    unittest.main()
