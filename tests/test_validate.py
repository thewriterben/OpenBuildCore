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
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
