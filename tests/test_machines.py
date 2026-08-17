"""Tests for machine capability checks. Stdlib unittest; no dependencies.

The point of most of these is that a check refuses rather than guesses: an
unmeasured machine yields no time estimate, and a placeholder envelope fails
loudly instead of passing on a number nobody sourced.
"""
import json
import sys
import tempfile
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

    def test_a_placeholder_envelope_still_fails_loudly(self):
        """The K2's envelope was a 1x1x1 TODO(source) until it was found in
        Creality Print's own machine profile. The behaviour that placeholder
        protected still matters for the next uncited machine, so it is pinned
        against a synthetic one rather than lost with the data that prompted
        it."""
        placeholder = dict(
            self.by_id["k2-plus"],
            machine_id="unmeasured",
            envelope_mm={"x": 1, "y": 1, "z": 1},
            source={"citation": "TODO(source): nobody has measured this bed."},
        )
        result = machines.evaluate(placeholder, (40, 30, 12), "petg", None, 9000)
        self.assertFalse(result["can_print"])
        self.assertIn("does not fit", result["blockers"][0])

    def test_the_k2_envelope_is_now_cited_and_usable(self):
        """350 x 350 x 350 from resources/profiles/Creality/machine/
        'Creality K2 Plus 0.4 nozzle.json' - printable_area and
        printable_height, the vendor's own profile for this exact machine."""
        k2 = self.by_id["k2-plus"]
        self.assertEqual({"x": 350, "y": 350, "z": 350}, k2["envelope_mm"])
        self.assertNotIn("TODO(source)", k2["source"]["citation"])
        self.assertIn("Creality Print", k2["source"]["citation"])
        self.assertTrue(
            machines.evaluate(k2, (40, 30, 12), "petg", None, 9000)["can_print"])

    def test_the_k2_still_offers_no_time(self):
        """A real envelope does not imply a measured throughput. The two are
        separate facts and only one of them has been sourced."""
        self.assertIsNone(self.by_id["k2-plus"]["measured_throughput"])

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


class SidecarTests(unittest.TestCase):
    """Taking a part's dimensions from an OpenDesignCore provenance record.

    The 0.2 fixture below is a real record, produced by `run-enclosure
    --voxel-mm 0.5` against parts/esp32-s3-wroom-1 with 0.30 mm clearance and a
    2.40 mm wall. Its bbox is exactly envelope + 2(clearance + wall) in x/y and
    wall + z + clearance in z, which is why it is worth pinning rather than
    inventing round numbers.
    """

    SIDECAR_02 = {
        "artifact": {
            "bbox_mm": {"x": "23.40", "y": "30.90", "z": "5.80"},
            "media_type": "model/stl",
            "sha256": "9d586f2da20ef1081ab7fee4ecb3a592fee7abe38d014a7bcd9f259c7b4a4127",
            "volume_cubic_mm": "2527.86",
        },
        "commit": "9ce67b1",
        "inputs": {"part_envelope_mm": {"x": "18.00", "y": "25.50", "z": "3.10"}},
        "model": "enclosure-shell/0.1",
        "schema": "odc/provenance/0.2",
        "voxel_size_mm": "0.50",
    }

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.dir = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def write(self, doc) -> Path:
        path = self.dir / "run.provenance.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def test_reads_size_and_volume(self):
        source = machines.load_sidecar(self.write(self.SIDECAR_02))
        self.assertEqual((23.40, 30.90, 5.80), source["size_mm"])
        self.assertAlmostEqual(2527.86, source["volume_mm3"])
        self.assertEqual("enclosure-shell/0.1", source["model"])

    def test_reads_the_artifact_not_the_part_envelope(self):
        """The distinction the refusal message exists to protect: the envelope
        is what goes inside, not what gets printed."""
        source = machines.load_sidecar(self.write(self.SIDECAR_02))
        self.assertNotEqual((18.0, 25.5, 3.1), source["size_mm"])

    def test_schema_01_is_refused_by_name(self):
        """0.1 records the inputs only. Guessing a size from the part envelope
        would be wrong by 2(clearance + wall) and would look plausible."""
        old = {
            "schema": "odc/provenance/0.1",
            "model": "enclosure-shell/0.1",
            "inputs": {"part_envelope_mm": {"x": "18.00", "y": "25.50", "z": "3.10"}},
            "artifact": {"media_type": "model/stl", "sha256": "deadbeef"},
        }
        with self.assertRaises(SystemExit) as caught:
            machines.load_sidecar(self.write(old))
        self.assertIn("odc/provenance/0.1", str(caught.exception))
        self.assertIn("0.2 or later", str(caught.exception))

    def test_a_later_schema_keeping_the_field_still_works(self):
        """The requirement is the field, not a version whitelist I would have
        to remember to widen."""
        future = dict(self.SIDECAR_02, schema="odc/provenance/0.9")
        self.assertEqual(
            (23.40, 30.90, 5.80), machines.load_sidecar(self.write(future))["size_mm"])

    def test_a_foreign_json_document_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            machines.load_sidecar(self.write({"schema": "something/else/1.0"}))
        self.assertIn("not an OpenDesignCore provenance record", str(caught.exception))

    def test_malformed_bbox_is_refused(self):
        broken = dict(self.SIDECAR_02)
        broken["artifact"] = dict(broken["artifact"], bbox_mm={"x": "1.0", "y": "2.0"})
        with self.assertRaises(SystemExit) as caught:
            machines.load_sidecar(self.write(broken))
        self.assertIn("malformed", str(caught.exception))

    def test_missing_file_is_refused(self):
        with self.assertRaises(SystemExit):
            machines.load_sidecar(self.dir / "nope.json")

    def test_a_real_record_drives_a_real_verdict(self):
        """End to end: an ODC design judged against the shipped machines."""
        source = machines.load_sidecar(self.write(self.SIDECAR_02))
        shipped = {m["machine_id"]: m for m in
                   machines.load_machines(ROOT / "example" / "machines.json")}

        bench = machines.evaluate(shipped["example-bench-fdm"], source["size_mm"],
                                  "petg", None, source["volume_mm3"])
        self.assertTrue(bench["can_print"])
        self.assertTrue(bench["time"]["known"], "volume came from the sidecar, not a flag")

        # The K2's envelope is real now (350 mm cubed, from Creality Print's
        # own profile), so a 23 x 31 x 6 mm enclosure fits it easily. What is
        # being checked is that a design's recorded dimensions drive a verdict
        # at all, not which way the verdict falls.
        k2 = machines.evaluate(shipped["k2-plus"], source["size_mm"],
                               "petg", None, source["volume_mm3"])
        self.assertTrue(k2["can_print"])
        self.assertFalse(k2["time"]["known"], "still no measured throughput")


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
