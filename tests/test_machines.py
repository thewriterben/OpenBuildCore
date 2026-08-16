"""Tests for machine capability checks. Stdlib unittest; no dependencies.

The point of most of these is that a check refuses rather than guesses: an
unmeasured machine yields no time estimate, and a placeholder envelope fails
loudly instead of passing on a number nobody sourced.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import machines  # noqa: E402

BENCH = {
    "machine_id": "bench", "make": "M", "model": "Bench", "process": "fdm",
    "envelope_mm": {"x": 220, "y": 220, "z": 250},
    "materials": ["pla", "petg"],
    "constraints": {"nozzle_diameter_mm": 0.4, "min_feature_mm": 0.8},
    "measured_throughput": {
        "cubic_mm_per_hour": 14000,
        "how_measured": "fictional",
        "measured_on": "2026-08-15",
    },
}

UNMEASURED = {
    "machine_id": "unmeasured", "make": "M", "model": "Quiet", "process": "fdm",
    "envelope_mm": {"x": 300, "y": 300, "z": 300},
    "materials": ["pla"],
    "constraints": {"nozzle_diameter_mm": 0.6},
    "measured_throughput": None,
}


class FitTests(unittest.TestCase):
    def test_fits_as_modelled(self):
        self.assertEqual(
            (0, 1, 2), machines.fit_orientation((40, 30, 12), BENCH["envelope_mm"]))

    def test_a_part_too_tall_flat_fits_stood_on_end(self):
        """240 mm exceeds the 220 mm bed but clears the 250 mm gantry."""
        envelope = BENCH["envelope_mm"]
        self.assertIsNone(machines.fit_orientation((240, 30, 12), {
            "x": 220, "y": 220, "z": 100}))
        permutation = machines.fit_orientation((240, 30, 12), envelope)
        self.assertIsNotNone(permutation)
        self.assertEqual(2, permutation.index(0), "the 240 mm axis must go to z")

    def test_no_orientation_fits(self):
        self.assertIsNone(
            machines.fit_orientation((400, 400, 400), BENCH["envelope_mm"]))

    def test_orientation_is_described_not_just_asserted(self):
        text = machines.describe_orientation((2, 1, 0), (240, 30, 12))
        self.assertIn("part z -> bed x", text)


class MaterialAndFeatureTests(unittest.TestCase):
    def test_unsupported_material_is_a_blocker(self):
        result = machines.evaluate(BENCH, (40, 30, 12), "abs", None, None)
        self.assertFalse(result["can_print"])
        self.assertIn("cannot run abs", result["blockers"][0])

    def test_explicit_min_feature_beats_nozzle_diameter(self):
        """0.5 mm clears the 0.4 mm nozzle but not the declared 0.8 mm floor."""
        self.assertEqual(0.8, machines.feature_floor_mm(BENCH))
        result = machines.evaluate(BENCH, (40, 30, 12), "petg", 0.5, None)
        self.assertFalse(result["can_print"])
        self.assertIn("below this machine's floor 0.8 mm", result["blockers"][0])

    def test_nozzle_diameter_is_the_fallback_floor(self):
        self.assertEqual(0.6, machines.feature_floor_mm(UNMEASURED))

    def test_no_declared_floor_means_unchecked_not_passed(self):
        machine = dict(UNMEASURED, constraints={})
        self.assertIsNone(machines.feature_floor_mm(machine))
        result = machines.evaluate(machine, (40, 30, 12), "pla", 0.01, None)
        self.assertTrue(result["can_print"])
        self.assertIn("feature size unchecked", " ".join(result["notes"]))


class TimeTests(unittest.TestCase):
    def test_no_measured_throughput_means_no_estimate(self):
        time = machines.estimate_hours(UNMEASURED, 9000)
        self.assertFalse(time["known"])
        self.assertIn("requires slicing", time["reason"])
        self.assertNotIn("hours", time)

    def test_estimate_carries_its_basis_and_its_caveat(self):
        time = machines.estimate_hours(BENCH, 14000)
        self.assertTrue(time["known"])
        self.assertAlmostEqual(1.0, time["hours"])
        self.assertEqual("fictional", time["basis"])
        self.assertIn("slicer supersedes", time["caveat"])

    def test_volume_is_required_even_with_a_measured_rate(self):
        time = machines.estimate_hours(BENCH, None)
        self.assertFalse(time["known"])
        self.assertIn("--volume-mm3", time["reason"])


class ShippedMachinesTests(unittest.TestCase):
    """The example file is data, and its placeholders must behave like placeholders."""

    def setUp(self):
        self.machines = machines.load_machines(ROOT / "example" / "machines.json")
        self.by_id = {m["machine_id"]: m for m in self.machines}

    def test_k2_plus_placeholder_envelope_fails_loudly(self):
        """envelope_mm is TODO(source) at 1x1x1: nothing may pass a fit check."""
        k2 = self.by_id["k2-plus"]
        self.assertIn("TODO(source)", k2["source"]["citation"])
        result = machines.evaluate(k2, (40, 30, 12), "petg", None, 9000)
        self.assertFalse(result["can_print"])
        self.assertIn("does not fit", result["blockers"][0])

    def test_k2_plus_offers_no_time_despite_a_volume(self):
        result = machines.evaluate(self.by_id["k2-plus"], (1, 1, 1), None, None, 9000)
        self.assertFalse(result["time"]["known"])

    def test_every_machine_carries_a_citation(self):
        for machine in self.machines:
            self.assertTrue(
                (machine.get("source") or {}).get("citation"),
                f"{machine['machine_id']} has no citation")

    def test_example_file_matches_the_schema_fields_it_claims(self):
        schema = json.loads(
            (ROOT / "schema" / "machine.schema.json").read_text(encoding="utf-8"))
        required = schema["required"]
        for machine in self.machines:
            for field in required:
                self.assertIn(field, machine, f"{machine['machine_id']} lacks {field}")


class ParsingTests(unittest.TestCase):
    def test_size_parses(self):
        self.assertEqual((40.0, 30.0, 12.0), machines.parse_size("40x30x12"))

    def test_two_dimensions_are_refused(self):
        with self.assertRaises(SystemExit):
            machines.parse_size("40x30")

    def test_non_numeric_is_refused(self):
        with self.assertRaises(SystemExit):
            machines.parse_size("40xbigx12")


if __name__ == "__main__":
    unittest.main()
