#!/usr/bin/env python3
"""Validate projects, inventory and machines, and that their references resolve.

    python scripts/validate.py [--parts <dir>] [--inventory <file>] [--machines <file>]

Structure is the easy half. The half that matters is **referential integrity**:

* a `part_id` no registry entry provides is a typo that will read as a gap
  forever, sending someone to buy a part that does not exist under that name;
* a `capability` no registry part provides makes a project **unbuildable by
  construction**: the advisor will report it short of something nothing can
  satisfy, and the suggestion list will be empty.

Both fail silently in the advisor: they look like ordinary gaps. So they are
caught here instead.

Machines get the same treatment for a different reason. Their fields are
physical claims about hardware, so an uncited capability or a throughput with
no `how_measured` is a recalled number that will be read as a measurement.

Made parts (`make`) are checked for shape only, never against owned machines:
projects are shareable, machines are personal, and a project's validity must
not depend on who is reading it.

Stdlib only; the JSON Schema files are the authoritative shape definition for
tooling that can consume them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ID_RE = re.compile(r"^(boards|electronic|mechanical|material)/[a-z0-9][a-z0-9._-]*$")
PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MACHINE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAKE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DIFFICULTIES = {"beginner", "intermediate", "advanced"}


def load_registry(parts_dir: Path) -> tuple[set, set]:
    """Known part ids, and every capability any part provides."""
    data_dir = parts_dir / "data"
    if not data_dir.exists():
        raise SystemExit(f"OpenPartsCore data not found at {data_dir}; pass --parts")
    ids, capabilities = set(), set()
    for path in sorted(data_dir.rglob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        ids.add(entry["id"])
        capabilities.update((entry.get("attributes") or {}).get("capabilities") or [])
    return ids, capabilities


def check_project(path: Path, ids: set, capabilities: set) -> list:
    errors = []

    def bad(message: str) -> None:
        errors.append(f"{path.name}: {message}")

    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]

    for field in ("schema_version", "id", "name", "description", "requires"):
        if field not in project:
            bad(f"missing required field '{field}'")
    if errors:
        return errors

    if project["schema_version"] != 0:
        bad(f"schema_version {project['schema_version']} != 0")
    if not PROJECT_ID_RE.match(project["id"]):
        bad(f"bad id '{project['id']}'")
    if project["id"] != path.stem:
        bad(f"id '{project['id']}' does not match filename '{path.stem}'")
    if "difficulty" in project and project["difficulty"] not in DIFFICULTIES:
        bad(f"difficulty '{project['difficulty']}' not one of {sorted(DIFFICULTIES)}")
    if not project["requires"]:
        bad("requires is empty; a project with no requirements is always buildable")

    for index, requirement in enumerate(project["requires"]):
        where = f"requires[{index}]"
        has_part = "part_id" in requirement
        has_cap = "capability" in requirement
        has_make = "make" in requirement
        if sum((has_part, has_cap, has_make)) != 1:
            bad(f"{where}: needs exactly one of part_id, capability or make")
            continue
        if requirement.get("qty", 1) < 1:
            bad(f"{where}: qty must be >= 1")

        if has_make:
            errors.extend(check_made_part(path, where, requirement))
        elif has_part:
            part_id = requirement["part_id"]
            if not ID_RE.match(part_id):
                bad(f"{where}: malformed part_id '{part_id}'")
            elif part_id not in ids:
                bad(f"{where}: part_id '{part_id}' is not in the registry: "
                    "this reads as a permanent gap and sends someone shopping "
                    "for a part that does not exist under that name")
        else:
            capability = requirement["capability"]
            if capability not in capabilities:
                bad(f"{where}: capability '{capability}' is provided by no registry "
                    "part, so this project is unbuildable by construction")
    return errors


def check_made_part(path: Path, where: str, requirement: dict) -> list:
    """A made part is checked for shape only, never against owned machines.

    Projects are shareable; machines are personal. A project needing ASA is a
    perfectly valid project for someone with no ASA-capable printer -- that is
    a capability gap the advisor reports, not an error in the file. Validating
    against machines would make a project's validity depend on who is reading
    it.

    What is checked: a size that can be compared to a build volume, and a
    declared material. A made part with no material cannot be judged at all,
    and defaulting one would be inventing a design decision.
    """
    errors = []

    def bad(message: str) -> None:
        errors.append(f"{path.name}: {where}: {message}")

    if not MAKE_ID_RE.match(requirement.get("make", "")):
        bad(f"malformed make name '{requirement.get('make')}'")

    size = requirement.get("size_mm")
    if not isinstance(size, dict):
        bad("needs size_mm {x, y, z} in mm; without it there is nothing to "
            "compare against a build volume")
    else:
        for axis in ("x", "y", "z"):
            value = size.get(axis)
            if not isinstance(value, (int, float)) or value <= 0:
                bad(f"size_mm.{axis} must be a number > 0")

    if not requirement.get("material"):
        bad("needs a material: a made part with no material cannot be checked "
            "against a machine, and defaulting one would invent a design decision")

    floor = requirement.get("min_feature_mm")
    if floor is not None and (not isinstance(floor, (int, float)) or floor <= 0):
        bad("min_feature_mm must be a number > 0 when present; absent means "
            "unchecked, which is not the same as zero")
    return errors


def check_axis_calibration(path: Path, where: str, machine: dict) -> list:
    """Axis calibration is optional to HAVE and strict once claimed.

    Absent means unknown, which downstream tooling treats as a reason not to
    write a material compensation into a slicer profile — not as a reason to
    refuse to measure. That distinction is the whole point: measuring an
    uncalibrated machine is useful, because the measurement is how you find
    out it is uncalibrated.

    What is refused is a half-made claim. A date with no residual, or a
    residual with no method, reads as "calibrated" to anything that checks and
    means nothing.
    """
    errors = []
    calibration = machine.get("axis_calibration")
    if calibration is None:
        return errors

    if not isinstance(calibration, dict):
        return [f"{path.name}: {where}: axis_calibration must be an object or absent"]

    for axis, entry in calibration.items():
        if axis not in ("x", "y", "z"):
            errors.append(f"{path.name}: {where}: axis_calibration has unknown axis '{axis}'")
            continue
        at = f"{where}: axis_calibration.{axis}"

        if not isinstance(entry, dict):
            errors.append(f"{path.name}: {at} must be an object")
            continue
        if not entry.get("verified_on"):
            errors.append(
                f"{path.name}: {at}: no verified_on. Calibration is perishable — belts "
                "stretch, pulleys creep — so an undated one is a claim nobody can check.")
        if not isinstance(entry.get("residual_pct"), (int, float)):
            errors.append(
                f"{path.name}: {at}: no residual_pct. Recording a calibration is a claim "
                "that a measurement happened, and a measurement has a result.")
        if not entry.get("how_measured"):
            errors.append(
                f"{path.name}: {at}: no how_measured. A residual with no method behind it "
                "is a number somebody could have typed.")
    return errors


def check_inventory(path: Path, ids: set) -> list:
    errors = []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]

    if doc.get("schema_version") != 0:
        errors.append(f"{path.name}: schema_version must be 0")
    for index, item in enumerate(doc.get("items", [])):
        where = f"items[{index}]"
        part_id = item.get("part_id", "")
        if not ID_RE.match(part_id):
            errors.append(f"{path.name}: {where}: malformed part_id '{part_id}'")
        elif part_id not in ids:
            errors.append(
                f"{path.name}: {where}: part_id '{part_id}' is not in the registry"
            )
        if item.get("qty", 1) < 1:
            errors.append(f"{path.name}: {where}: qty must be >= 1")
    return errors


def check_machines(path: Path) -> list:
    """Machines describe physical hardware, so the checks are about sourcing.

    The one that earns its place is `measured_throughput`: a rate with no
    `how_measured` is indistinguishable from a number somebody recalled, and
    it would silently become a print-time estimate the user trusts.
    """
    errors = []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]

    if doc.get("schema_version") != 0:
        errors.append(f"{path.name}: schema_version must be 0")

    seen = set()
    for index, machine in enumerate(doc.get("machines", [])):
        where = f"machines[{index}]"
        machine_id = machine.get("machine_id", "")
        if not MACHINE_ID_RE.match(machine_id):
            errors.append(f"{path.name}: {where}: malformed machine_id '{machine_id}'")
        elif machine_id in seen:
            errors.append(f"{path.name}: {where}: duplicate machine_id '{machine_id}'")
        seen.add(machine_id)

        for field in ("make", "model", "process", "envelope_mm", "materials"):
            if field not in machine:
                errors.append(f"{path.name}: {where}: missing '{field}'")

        envelope = machine.get("envelope_mm") or {}
        for axis in ("x", "y", "z"):
            value = envelope.get(axis)
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"{path.name}: {where}: envelope_mm.{axis} must be > 0")

        if not (machine.get("source") or {}).get("citation"):
            errors.append(
                f"{path.name}: {where}: no source.citation. Capabilities are physical "
                "facts about hardware; an uncited one is a guess wearing a number."
            )

        errors.extend(check_axis_calibration(path, where, machine))

        throughput = machine.get("measured_throughput")
        if throughput is not None:
            rate = throughput.get("cubic_mm_per_hour")
            if not isinstance(rate, (int, float)) or rate <= 0:
                errors.append(
                    f"{path.name}: {where}: measured_throughput.cubic_mm_per_hour must be > 0")
            if not throughput.get("how_measured"):
                errors.append(
                    f"{path.name}: {where}: measured_throughput has no how_measured. "
                    "Set it only from a print you timed, and say how."
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parts", type=Path, default=ROOT.parent / "OpenPartsCore")
    parser.add_argument("--inventory", type=Path, default=ROOT / "example" / "inventory.json")
    parser.add_argument("--machines", type=Path, default=ROOT / "example" / "machines.json")
    args = parser.parse_args()

    ids, capabilities = load_registry(args.parts)
    failures = []

    projects = sorted((ROOT / "data" / "projects").glob("*.json"))
    if not projects:
        print("no projects found under data/projects", file=sys.stderr)
        return 1
    for path in projects:
        failures.extend(check_project(path, ids, capabilities))

    if args.inventory.exists():
        failures.extend(check_inventory(args.inventory, ids))
    machine_count = 0
    if args.machines.exists():
        failures.extend(check_machines(args.machines))
        machine_count = len(
            json.loads(args.machines.read_text(encoding="utf-8")).get("machines", []))

    for failure in failures:
        print(f"FAIL {failure}")
    print(
        f"{len(projects)} project(s) checked against {len(ids)} registry part(s) "
        f"and {len(capabilities)} capability token(s), plus {machine_count} machine(s); "
        f"{'all valid' if not failures else str(len(failures)) + ' problem(s)'}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
