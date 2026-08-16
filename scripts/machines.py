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

    if not args.size:
        print("can-print needs --size XxYxZ (mm)", file=sys.stderr)
        return 2
    part = parse_size(args.size)

    results = [
        evaluate(m, part, args.material, args.min_feature_mm, args.volume_mm3)
        for m in machines
    ]
    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    render_results(results)
    capable = [r for r in results if r["can_print"]]
    print(f"{len(capable)} of {len(results)} machine(s) can make this part.")
    return 0 if capable else 1


if __name__ == "__main__":
    sys.exit(main())
