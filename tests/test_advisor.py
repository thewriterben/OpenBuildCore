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
import machines as machines_lib  # noqa: E402

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


class ShoppingListTests(unittest.TestCase):
    """The sequential/simultaneous distinction: under-ordering is the failure."""

    def setUp(self):
        needs_one = {"id": "a", "name": "A", "requires": [{"capability": "lora", "qty": 1}]}
        needs_two = {"id": "b", "name": "B", "requires": [{"capability": "lora", "qty": 2}]}
        self.results = [
            advisor.evaluate(needs_one, {}, REGISTRY),
            advisor.evaluate(needs_two, {}, REGISTRY),
        ]

    def test_sequential_builds_reuse_parts_so_quantity_is_the_max(self):
        items = advisor.shopping_list(self.results, simultaneous=False)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["qty"], 2)

    def test_simultaneous_builds_need_the_sum(self):
        items = advisor.shopping_list(self.results, simultaneous=True)
        self.assertEqual(items[0]["qty"], 3)

    def test_items_record_which_projects_they_unlock(self):
        items = advisor.shopping_list(self.results, simultaneous=False)
        self.assertEqual(sorted(items[0]["unlocks"]), ["a", "b"])

    def test_nothing_to_buy_when_everything_is_buildable(self):
        buildable = advisor.evaluate(
            {"id": "c", "name": "C", "requires": [{"capability": "lora", "qty": 1}]},
            {"boards/radio": 1},
            REGISTRY,
        )
        self.assertEqual(advisor.shopping_list([buildable], simultaneous=False), [])


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


BENCH = {
    "machine_id": "bench", "make": "M", "model": "Bench", "process": "fdm",
    "envelope_mm": {"x": 220, "y": 220, "z": 250},
    "materials": ["pla", "petg"],
    "constraints": {"nozzle_diameter_mm": 0.4},
    "measured_throughput": None,
}


def with_made_part(**overrides) -> dict:
    made = {"make": "bracket", "size_mm": {"x": 40, "y": 30, "z": 12},
            "material": "petg", "qty": 1}
    made.update(overrides)
    return {
        "id": "p", "name": "Project",
        "requires": [{"capability": "gpio", "qty": 1}, made],
    }


class MadePartTests(unittest.TestCase):
    """Made parts are a different question from shopping, and stay separate.

    A project short a LoRa radio is fixed by buying one. A project needing a
    260 mm bracket on a 220 mm bed is not fixed by buying anything, so the two
    must not collapse into one "missing" bucket.
    """

    OWNED = {"boards/mcu": 1}

    def evaluate(self, project, machines):
        return advisor.evaluate(project, self.OWNED, REGISTRY, machines)

    def test_a_makeable_part_does_not_block(self):
        result = self.evaluate(with_made_part(), [BENCH])
        self.assertTrue(result["buildable"])
        self.assertTrue(result["makeable"])
        self.assertEqual("makeable", result["fabricate"][0]["status"])

    def test_a_part_no_machine_can_make_leaves_the_parts_half_satisfied(self):
        """The distinction that earns the second boolean: every part is owned,
        and the project still cannot be finished."""
        result = self.evaluate(
            with_made_part(size_mm={"x": 24, "y": 18, "z": 260}), [BENCH])
        self.assertTrue(result["buildable"], "the parts half is fine")
        self.assertFalse(result["makeable"])
        self.assertEqual([], result["gaps"], "an unmakeable part is not a parts gap")
        self.assertEqual("no_machine", result["fabricate"][0]["status"])

    def test_wrong_material_blocks_as_surely_as_wrong_size(self):
        result = self.evaluate(with_made_part(material="asa"), [BENCH])
        self.assertFalse(result["makeable"])
        blockers = result["fabricate"][0]["machines"][0]["blockers"]
        self.assertTrue(any("cannot run asa" in b for b in blockers), blockers)

    def test_no_machines_declared_is_unknown_not_cannot(self):
        """Absence of evidence recorded as absence, like an undeclared scanner
        accuracy in OpenDesignCore."""
        result = self.evaluate(with_made_part(), None)
        self.assertIsNone(result["makeable"])
        self.assertEqual("unknown", result["fabricate"][0]["status"])
        self.assertTrue(result["buildable"])

    def test_a_project_with_no_made_parts_is_makeable_vacuously(self):
        project = {"id": "p", "name": "P",
                   "requires": [{"capability": "gpio", "qty": 1}]}
        result = advisor.evaluate(project, self.OWNED, REGISTRY, None)
        self.assertTrue(result["makeable"])
        self.assertEqual([], result["fabricate"])

    def test_made_parts_never_reach_the_shopping_list(self):
        """Buying more parts cannot fix a bed that is too small, so an
        unmakeable part on a shopping list would sit unbought forever looking
        like an ordering oversight."""
        result = self.evaluate(
            with_made_part(size_mm={"x": 24, "y": 18, "z": 260}), [BENCH])
        items = advisor.shopping_list([result], simultaneous=False)
        self.assertEqual([], items)

    def test_a_made_part_does_not_consume_owned_stock(self):
        """It is fabricated, not allocated: it must not compete with the
        electronics for the one board in the drawer."""
        project = with_made_part()
        result = self.evaluate(project, [BENCH])
        allocated = result["satisfied"][0]["allocated"]
        self.assertEqual([{"part_id": "boards/mcu", "qty": 1}], allocated)

    def test_status_label_names_which_half_failed(self):
        parts_short = advisor.evaluate(
            with_made_part(), {}, REGISTRY, [BENCH])
        self.assertEqual("MISSING PARTS", advisor.status_of(parts_short))

        machine_short = self.evaluate(
            with_made_part(size_mm={"x": 24, "y": 18, "z": 260}), [BENCH])
        self.assertEqual("NO MACHINE", advisor.status_of(machine_short))

        both = advisor.evaluate(
            with_made_part(size_mm={"x": 24, "y": 18, "z": 260}), {}, REGISTRY, [BENCH])
        self.assertEqual("BLOCKED", advisor.status_of(both))

        unknown = self.evaluate(with_made_part(), None)
        self.assertEqual("PARTS OK, MACHINES UNKNOWN", advisor.status_of(unknown))


class ShippedDataTests(unittest.TestCase):
    def test_shipped_made_parts_exercise_every_blocker_kind(self):
        """The catalogue must not only contain parts every machine can make,
        or the negative paths ship untested.

        This originally required a globally unmakeable part, which held while
        the K2's envelope was an unsourced 1x1x1 placeholder. Once the real
        350 mm cubed envelope was found in Creality Print's own profile,
        nothing in the catalogue was unmakeable *everywhere* - a 350 mm
        printer makes most hobby parts. Inventing a project purely to fail
        would be data that serves the test rather than the user.

        So the invariant is stated where it actually lives: shipped parts must
        still exercise both kinds of refusal on some machine. The 260 mm probe
        stake exceeds the bench's 250 mm gantry; the ASA housing exceeds its
        materials. Both are real constraints, not contrivances.
        """
        projects = advisor.load_projects(advisor.ROOT / "data" / "projects")
        machines = machines_lib.load_machines(
            advisor.ROOT / "example" / "machines.json")
        registry = {"boards/mcu": REGISTRY["boards/mcu"]}

        statuses, blockers = [], []
        for project in projects:
            for made in advisor.evaluate(project, {}, registry, machines)["fabricate"]:
                statuses.append(made["status"])
                for verdict in made["machines"]:
                    blockers.extend(verdict["blockers"])

        self.assertTrue(statuses, "no shipped project declares a part to be made")
        self.assertIn("makeable", statuses)
        self.assertTrue(any("does not fit" in b for b in blockers),
                        "no shipped part exercises a size blocker")
        self.assertTrue(any("cannot run" in b for b in blockers),
                        "no shipped part exercises a material blocker")

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
