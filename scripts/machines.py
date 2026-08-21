#!/usr/bin/env python3
"""Which of your machines can make this, and what stops the others.

    python scripts/machines.py list
    python scripts/machines.py can-print --size 40x30x12 --material petg
    python scripts/machines.py can-print --size 40x30x12 --material petg --volume-mm3 9000

Answers four questions per machine, each deterministic:

* Fit - does the part fit the build envelope, in any axis-aligned orientation?
  A part that fails flat may fit stood on end, so all six permutations are
  tried and the one that works is named.
* Material - can the machine actually run it? Declared per machine.
* Feature size - is the smallest declared feature above the machine's floor
  (an explicit min_feature_mm, else the nozzle diameter)?
* Time - only when the machine carries a throughput its owner measured.
  Otherwise the answer is "requires slicing", because a slicer is the only
  honest source and a volumetric guess would be a number with no provenance.

Rotation here is axis-aligned only. Arbitrary orientations can fit parts that
these six cannot, and finding them is a slicer's or a human's job.

Output is ASCII: these strings land in Windows consoles under cp1252.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MACHINES = ROOT / "example" / "machines.json"

AXIS_NAMES = ("x", "y", "z")


def load_machines(path: Path) -> list:
    if not path.exists():
        raise SystemExit(
            f"no machines file at {path}. Copy example/machines.json and edit it, "
            "or pass --machines."
        )
    doc = json.loads(path.read_text(encoding="utf-8"))
    machines = doc.get("machines", [])
    if not machines:
        raise SystemExit(f"{path} declares no machines")
    return machines


def fit_orientation(part_mm: tuple, envelope: dict) -> tuple | None:
    """First axis-aligned orientation that fits, or None.

    Returned as the permutation actually used, so the caller can say "stand it
    on end" rather than just "yes".
    """
    limits = (envelope["x"], envelope["y"], envelope["z"])
    for permutation in itertools.permutations(range(3)):
        oriented = tuple(part_mm[i] for i in permutation)
        if all(oriented[axis] <= limits[axis] for axis in range(3)):
            return permutation
    return None


def describe_orientation(permutation: tuple, part_mm: tuple) -> str:
    oriented = tuple(round(part_mm[i], 2) for i in permutation)
    if permutation == (0, 1, 2):
        return f"as modelled ({oriented[0]} x {oriented[1]} x {oriented[2]} mm)"
    mapping = ", ".join(
        f"part {AXIS_NAMES[src]} -> bed {AXIS_NAMES[dst]}"
        for dst, src in enumerate(permutation)
    )
    return f"rotated ({mapping})"


def feature_floor_mm(machine: dict) -> float | None:
    """Smallest feature the machine can be expected to render.

    An explicit min_feature_mm wins. Otherwise the nozzle diameter, which is a
    genuine physical floor for FDM: a feature thinner than one extrusion width
    has nowhere to go. If neither is declared there is no floor to check
    against, and the check is skipped rather than assumed.
    """
    constraints = machine.get("constraints") or {}
    if constraints.get("min_feature_mm"):
        return float(constraints["min_feature_mm"])
    if constraints.get("nozzle_diameter_mm"):
        return float(constraints["nozzle_diameter_mm"])
    return None


def estimate_hours(machine: dict, volume_mm3: float | None) -> dict:
    """Time, only from a measured figure. Never from a model."""
    throughput = machine.get("measured_throughput")
    if not throughput:
        return {
            "known": False,
            "reason": "no measured throughput on this machine - print time requires slicing",
        }
    if volume_mm3 is None:
        return {"known": False, "reason": "no part volume supplied (--volume-mm3)"}
    hours = volume_mm3 / float(throughput["cubic_mm_per_hour"])
    return {
        "known": True,
        "hours": hours,
        "basis": throughput["how_measured"],
        "caveat": (
            "pre-slicing triage only: bulk volume over one measured rate, "
            "ignoring travel, infill pattern, supports and cooling. A slicer "
            "supersedes this number entirely."
        ),
    }


def evaluate(machine: dict, part_mm: tuple, material: str | None,
             min_feature_mm: float | None, volume_mm3: float | None) -> dict:
    blockers, notes = [], []

    permutation = fit_orientation(part_mm, machine["envelope_mm"])
    if permutation is None:
        envelope = machine["envelope_mm"]
        blockers.append(
            f"does not fit: part {part_mm[0]} x {part_mm[1]} x {part_mm[2]} mm "
            f"vs envelope {envelope['x']} x {envelope['y']} x {envelope['z']} mm, "
            "in any axis-aligned orientation"
        )
    else:
        notes.append("fits " + describe_orientation(permutation, part_mm))

    if material:
        supported = [m.lower() for m in machine.get("materials", [])]
        if material.lower() not in supported:
            blockers.append(
                f"cannot run {material}: declares "
                f"{', '.join(supported) or 'no materials'}"
            )

    floor = feature_floor_mm(machine)
    if min_feature_mm is not None:
        if floor is None:
            notes.append("no feature floor declared - feature size unchecked")
        elif min_feature_mm < floor:
            blockers.append(
                f"smallest feature {min_feature_mm} mm is below this machine's "
                f"floor {floor} mm"
            )

    return {
        "machine_id": machine["machine_id"],
        "name": f"{machine['make']} {machine['model']}",
        "process": machine["process"],
        "can_print": not blockers,
        "blockers": blockers,
        "notes": notes,
        "time": estimate_hours(machine, volume_mm3),
    }


def parse_size(text: str) -> tuple:
    parts = text.lower().replace(" ", "").split("x")
    if len(parts) != 3:
        raise SystemExit(f"--size must be XxYxZ in mm, got '{text}'")
    try:
        return tuple(float(p) for p in parts)
    except ValueError as exc:
        raise SystemExit(f"--size must be numeric, got '{text}'") from exc


SIDECAR_PREFIX = "odc/provenance/"


def load_sidecar(path: Path) -> dict:
    """Take a part's dimensions from an OpenDesignCore provenance record.

    Better than a hand-typed --size for the reason provenance exists at all:
    the numbers came from the geometry that will be printed, and the answer can
    name the artifact it judged.

    The requirement checked here is the *field*, not a version number. A record
    that carries artifact.bbox_mm works whatever its schema says; one that does
    not is refused with the schema named, so the user knows which record they
    handed over rather than being told a dimension nobody measured.

    Material is deliberately not read from the sidecar. OpenDesignCore designs
    geometry and does not know what it will be printed in, so material stays a
    caller's declaration.
    """
    if not path.exists():
        raise SystemExit(f"no sidecar at {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from exc

    schema = doc.get("schema", "")
    if not schema.startswith(SIDECAR_PREFIX):
        raise SystemExit(
            f"{path} is not an OpenDesignCore provenance record "
            f"(schema '{schema or 'absent'}', expected one starting '{SIDECAR_PREFIX}')"
        )

    artifact = doc.get("artifact") or {}
    bbox = artifact.get("bbox_mm")
    if not bbox:
        raise SystemExit(
            f"{path} is schema '{schema}', which does not record the artifact's own "
            "dimensions - only its inputs. Re-run the design with a tool version "
            "that emits odc/provenance/0.2 or later (OpenDesignCore ADR-0010). "
            "Refusing rather than guessing a size from the part envelope, which is "
            "the part that goes inside, not the thing that gets printed."
        )

    try:
        size_mm = tuple(float(bbox[axis]) for axis in ("x", "y", "z"))
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"{path}: artifact.bbox_mm is malformed: {bbox}") from exc

    volume = artifact.get("volume_cubic_mm")
    return {
        "size_mm": size_mm,
        "volume_mm3": float(volume) if volume is not None else None,
        "schema": schema,
        "model": doc.get("model", "unknown"),
        "artifact_sha256": artifact.get("sha256", "unknown"),
        "voxel_size_mm": doc.get("voxel_size_mm"),
    }


def calibration_state(machine: dict) -> dict:
    """Whether this machine's axes have been verified, and how recently.

    Deliberately three states rather than two. "Unknown" is not "bad": a
    machine nobody has measured might be perfect, and measuring it is exactly
    how you would find out. What unknown *does* mean is that a material
    shrinkage figure taken here would be part material and part machine, filed
    under the material's name — so tooling declines to write one into a slicer
    profile, while still recording the measurement. That is OpenDesignCore
    ADR-0009's line: measuring is fine, writing something that shapes every
    future print is not.
    """
    calibration = machine.get("axis_calibration")
    if not calibration:
        return {
            "state": "unknown",
            "axes": [],
            "reason": "no axis calibration recorded. A shrinkage figure measured here would "
                      "mix material with machine error under the material's name.",
        }

    verified = sorted(calibration)
    missing = [a for a in ("x", "y", "z") if a not in calibration]
    if missing:
        return {
            "state": "partial",
            "axes": verified,
            "reason": f"axes {', '.join(verified)} verified; {', '.join(missing)} not. "
                      "A part is measured on all three.",
        }

    worst = max(abs(float(calibration[a]["residual_pct"])) for a in verified)
    return {
        "state": "verified",
        "axes": verified,
        "worst_residual_pct": worst,
        "reason": f"all three axes verified, worst residual {worst:.3f}%.",
    }


def render_list(machines: list) -> None:
    for machine in machines:
        envelope = machine["envelope_mm"]
        print(f"  {machine['machine_id']:<20} {machine['make']} {machine['model']} "
              f"[{machine['process']}, tier {machine.get('tier', '?')}]")
        print(f"       envelope {envelope['x']} x {envelope['y']} x {envelope['z']} mm; "
              f"materials: {', '.join(machine.get('materials', [])) or 'none declared'}")
        throughput = machine.get("measured_throughput")
        print("       throughput: "
              + (f"{throughput['cubic_mm_per_hour']} mm3/h (measured)" if throughput
                 else "not measured - print time requires slicing"))
        if "TODO(source)" in (machine.get("source") or {}).get("citation", ""):
            print("       !! citation carries a TODO(source): some values are placeholders")


def render_results(results: list) -> None:
    for result in results:
        mark = "CAN PRINT" if result["can_print"] else "CANNOT"
        print(f"[{mark}] {result['name']}  ({result['machine_id']})")
        for note in result["notes"]:
            print(f"    ok   {note}")
        for blocker in result["blockers"]:
            print(f"    NO   {blocker}")
        time = result["time"]
        if time["known"]:
            print(f"    time ~{time['hours']:.1f} h - {time['caveat']}")
        else:
            print(f"    time unknown: {time['reason']}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Which of your machines can make this, and what stops the others.")
    parser.add_argument("command", choices=["list", "can-print"])
    parser.add_argument("--machines", type=Path, default=DEFAULT_MACHINES)
    parser.add_argument("--size", help="part bounding box, XxYxZ in mm")
    parser.add_argument("--from-sidecar", type=Path, default=None,
                        help="take size and volume from an OpenDesignCore provenance record")
    parser.add_argument("--material", help="material token, e.g. petg")
    parser.add_argument("--min-feature-mm", type=float, default=None)
    parser.add_argument("--volume-mm3", type=float, default=None,
                        help="part volume; used only when a machine has measured throughput")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    machines = load_machines(args.machines)

    if args.command == "list":
        if args.json:
            print(json.dumps(machines, indent=2))
        else:
            render_list(machines)
        return 0

    if args.size and args.from_sidecar:
        print("give --size or --from-sidecar, not both: they are two answers to "
              "the same question and silently preferring one would hide a "
              "disagreement between the design and what was typed", file=sys.stderr)
        return 2

    source = None
    if args.from_sidecar:
        source = load_sidecar(args.from_sidecar)
        part = source["size_mm"]
        volume = args.volume_mm3 if args.volume_mm3 is not None else source["volume_mm3"]
    elif args.size:
        part = parse_size(args.size)
        volume = args.volume_mm3
    else:
        print("can-print needs --size XxYxZ (mm) or --from-sidecar <file>", file=sys.stderr)
        return 2

    results = [
        evaluate(m, part, args.material, args.min_feature_mm, volume)
        for m in machines
    ]
    if args.json:
        print(json.dumps({"source": source, "machines": results}, indent=2))
        return 0

    if source:
        print(f"Part from {source['model']} artifact sha256:{source['artifact_sha256'][:12]} "
              f"({source['schema']})")
        print(f"  {part[0]} x {part[1]} x {part[2]} mm"
              + (f", {volume} mm3" if volume is not None else "")
              + (f", voxel {source['voxel_size_mm']} mm" if source["voxel_size_mm"] else ""))
        print()

    render_results(results)
    capable = [r for r in results if r["can_print"]]
    print(f"{len(capable)} of {len(results)} machine(s) can make this part.")
    return 0 if capable else 1


if __name__ == "__main__":
    sys.exit(main())
