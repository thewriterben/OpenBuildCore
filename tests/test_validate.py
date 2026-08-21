"""Tests for the validator — including that it fails when it should.

A validator that never rejects anything reports "all valid" forever and reads
as coverage while providing none. Same lesson as OpenCircuitCore ADR-0006:
prove it fires.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import validate  # noqa: E402

IDS = {"boards/mcu", "electronic/sensor"}
CAPS = {"gpio", "sensor_read"}


def write(directory: Path, name: str, doc: dict) -> Path:
    path = directory / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def project(**overrides) -> dict:
    doc = {
        "schema_version": 0,
        "id": "thing",
        "name": "Thing",
        "description": "A thing.",
        "requires": [{"capability": "gpio", "qty": 1}],
    }
    doc.update(overrides)
    return doc


class ReferentialIntegrityTests(unittest.TestCase):
    """The checks that matter: references that silently read as gaps."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.dir = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def test_valid_project_passes(self):
        path = write(self.dir, "thing.json", project())
        self.assertEqual(validate.check_project(path, IDS, CAPS), [])

    def test_unknown_part_id_is_rejected(self):
        path = write(self.dir, "thing.json", project(
            requires=[{"part_id": "electronic/nope", "qty": 1}]))
        errors = validate.check_project(path, IDS, CAPS)
        self.assertTrue(any("not in the registry" in e for e in errors), errors)

    def test_capability_no_part_provides_is_rejected(self):
        """Unbuildable by construction: the advisor would report it as an
        ordinary gap forever, with an empty suggestion list."""
        path = write(self.dir, "thing.json", project(
            requires=[{"capability": "telepathy", "qty": 1}]))
        errors = validate.check_project(path, IDS, CAPS)
        self.assertTrue(any("unbuildable by construction" in e for e in errors), errors)

    def test_requirement_with_both_kinds_is_rejected(self):
        path = write(self.dir, "thing.json", project(
            requires=[{"part_id": "boards/mcu", "capability": "gpio"}]))
        errors = validate.check_project(path, IDS, CAPS)
        self.assertTrue(any("exactly one of" in e for e in errors), errors)

    def test_a_made_part_is_a_third_kind_and_is_accepted(self):
        path = write(self.dir, "thing.json", project(requires=[{
            "make": "bracket", "size_mm": {"x": 40, "y": 30, "z": 12},
            "material": "petg", "qty": 1,
        }]))
        self.assertEqual(validate.check_project(path, IDS, CAPS), [])

    def test_a_made_part_alongside_a_part_id_is_rejected(self):
        path = write(self.dir, "thing.json", project(requires=[{
            "make": "bracket", "part_id": "boards/mcu",
            "size_mm": {"x": 1, "y": 1, "z": 1}, "material": "petg",
        }]))
        errors = validate.check_project(path, IDS, CAPS)
        self.assertTrue(any("exactly one of" in e for e in errors), errors)

    def test_a_made_part_without_a_material_is_rejected(self):
        """It could not be checked against a machine at all, and defaulting a
        material would invent a design decision."""
        path = write(self.dir, "thing.json", project(requires=[{
            "make": "bracket", "size_mm": {"x": 40, "y": 30, "z": 12},
        }]))
        errors = validate.check_project(path, IDS, CAPS)
        self.assertTrue(any("needs a material" in e for e in errors), errors)

    def test_a_made_part_without_a_size_is_rejected(self):
        path = write(self.dir, "thing.json", project(requires=[{
            "make": "bracket", "material": "petg",
        }]))
        errors = validate.check_project(path, IDS, CAPS)
        self.assertTrue(any("size_mm" in e for e in errors), errors)

    def test_a_made_part_with_a_zero_axis_is_rejected(self):
        path = write(self.dir, "thing.json", project(requires=[{
            "make": "bracket", "material": "petg",
            "size_mm": {"x": 40, "y": 0, "z": 12},
        }]))
        errors = validate.check_project(path, IDS, CAPS)
        self.assertTrue(any("size_mm.y" in e for e in errors), errors)

    def test_a_made_part_is_not_checked_against_owned_machines(self):
        """Projects are shareable, machines are personal. A project needing ASA
        is valid for someone with no ASA-capable printer; that is a capability
        gap the advisor reports, not an error in the file."""
        path = write(self.dir, "thing.json", project(requires=[{
            "make": "housing", "material": "unobtainium",
            "size_mm": {"x": 9000, "y": 9000, "z": 9000},
        }]))
        self.assertEqual(validate.check_project(path, IDS, CAPS), [])

    def test_id_must_match_filename(self):
        path = write(self.dir, "other.json", project())
        errors = validate.check_project(path, IDS, CAPS)
        self.assertTrue(any("does not match filename" in e for e in errors), errors)

    def test_empty_requires_is_rejected(self):
        path = write(self.dir, "thing.json", project(requires=[]))
        errors = validate.check_project(path, IDS, CAPS)
        self.assertTrue(any("always buildable" in e for e in errors), errors)

    def test_bad_difficulty_is_rejected(self):
        path = write(self.dir, "thing.json", project(difficulty="trivial"))
        errors = validate.check_project(path, IDS, CAPS)
        self.assertTrue(any("difficulty" in e for e in errors), errors)

    def test_inventory_unknown_part_is_rejected(self):
        path = write(self.dir, "inv.json", {
            "schema_version": 0,
            "items": [{"part_id": "boards/ghost", "qty": 1}],
        })
        errors = validate.check_inventory(path, IDS)
        self.assertTrue(any("not in the registry" in e for e in errors), errors)


def machine(**overrides) -> dict:
    doc = {
        "schema_version": 0,
        "machine_id": "bench",
        "make": "M",
        "model": "Bench",
        "process": "fdm",
        "envelope_mm": {"x": 220, "y": 220, "z": 250},
        "materials": ["pla"],
        "source": {"citation": "measured with calipers", "retrieved": "2026-08-15"},
    }
    doc.update(overrides)
    return doc


class MachineValidationTests(unittest.TestCase):
    """Machine fields are physical claims, so the checks are about sourcing."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.dir = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def check(self, *machines_) -> list:
        path = write(self.dir, "machines.json",
                     {"schema_version": 0, "machines": list(machines_)})
        return validate.check_machines(path)

    def test_valid_machine_passes(self):
        self.assertEqual(self.check(machine()), [])

    def test_uncited_machine_is_rejected(self):
        errors = self.check(machine(source={}))
        self.assertTrue(any("no source.citation" in e for e in errors), errors)

    def test_throughput_without_how_measured_is_rejected(self):
        """The check that earns its place: an unsourced rate becomes a time
        estimate the user trusts."""
        errors = self.check(machine(
            measured_throughput={"cubic_mm_per_hour": 14000}))
        self.assertTrue(any("no how_measured" in e for e in errors), errors)

    def test_throughput_with_how_measured_passes(self):
        self.assertEqual(self.check(machine(measured_throughput={
            "cubic_mm_per_hour": 14000, "how_measured": "timed a 100 g benchy"})), [])

    def test_absent_throughput_is_fine(self):
        """Absence is the honest default, not an error."""
        self.assertEqual(self.check(machine(measured_throughput=None)), [])

    def test_zero_envelope_axis_is_rejected(self):
        errors = self.check(machine(envelope_mm={"x": 220, "y": 0, "z": 250}))
        self.assertTrue(any("envelope_mm.y must be > 0" in e for e in errors), errors)

    def test_duplicate_machine_id_is_rejected(self):
        errors = self.check(machine(), machine())
        self.assertTrue(any("duplicate machine_id" in e for e in errors), errors)

    def test_an_uncalibrated_machine_is_valid(self):
        """Absent means unknown, and unknown is not an error. Measuring an
        uncalibrated machine is how you find out it is uncalibrated — refusing
        to record one would block the diagnosis."""
        self.assertEqual(self.check(machine(axis_calibration=None)), [])

    def test_a_calibration_without_a_date_is_rejected(self):
        """Calibration is perishable. Belts stretch, pulleys creep."""
        errors = self.check(machine(axis_calibration={
            "y": {"residual_pct": 0.03, "how_measured": "caliper"}}))
        self.assertTrue(any("no verified_on" in e for e in errors), errors)

    def test_a_calibration_without_a_residual_is_rejected(self):
        """Claiming a calibration is claiming a measurement happened, and a
        measurement has a result."""
        errors = self.check(machine(axis_calibration={
            "y": {"verified_on": "2026-08-17", "how_measured": "caliper"}}))
        self.assertTrue(any("no residual_pct" in e for e in errors), errors)

    def test_a_residual_without_a_method_is_rejected(self):
        errors = self.check(machine(axis_calibration={
            "y": {"verified_on": "2026-08-17", "residual_pct": 0.03}}))
        self.assertTrue(any("no how_measured" in e for e in errors), errors)

    def test_a_zero_residual_is_allowed_but_must_still_be_declared(self):
        """Zero is suspicious rather than excellent, and the schema says so —
        but refusing it outright would be the tool overruling a measurement."""
        self.assertEqual(self.check(machine(axis_calibration={
            "y": {"verified_on": "2026-08-17", "residual_pct": 0.0,
                  "how_measured": "block + caliper 0.02 mm"}})), [])

    def test_an_unknown_axis_is_rejected(self):
        errors = self.check(machine(axis_calibration={
            "w": {"verified_on": "2026-08-17", "residual_pct": 0.0,
                  "how_measured": "caliper"}}))
        self.assertTrue(any("unknown axis 'w'" in e for e in errors), errors)

    def test_a_fully_declared_calibration_passes(self):
        self.assertEqual(self.check(machine(axis_calibration={
            "x": {"verified_on": "2026-08-17", "residual_pct": 0.04,
                  "how_measured": "calibration-block/0.2, caliper 0.02 mm",
                  "rotation_distance": 40.012}})), [])

    def test_missing_field_is_rejected(self):
        doc = machine()
        del doc["materials"]
        errors = self.check(doc)
        self.assertTrue(any("missing 'materials'" in e for e in errors), errors)


class ShippedDataTests(unittest.TestCase):
    def test_every_shipped_project_and_the_example_inventory_validate(self):
        parts = validate.ROOT.parent / "OpenPartsCore"
        if not (parts / "data").exists():
            self.skipTest("OpenPartsCore not checked out alongside this repo")
        ids, capabilities = validate.load_registry(parts)
        failures = []
        for path in sorted((validate.ROOT / "data" / "projects").glob("*.json")):
            failures.extend(validate.check_project(path, ids, capabilities))
        failures.extend(
            validate.check_inventory(validate.ROOT / "example" / "inventory.json", ids)
        )
        failures.extend(
            validate.check_machines(validate.ROOT / "example" / "machines.json")
        )
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
