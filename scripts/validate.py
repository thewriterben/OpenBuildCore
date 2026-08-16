#!/usr/bin/env python3
"""Validate projects and inventory, including that their references resolve.

    python scripts/validate.py [--parts <OpenPartsCore dir>] [--inventory <file>]

Structure is the easy half. The half that matters is **referential integrity**:

* a `part_id` no registry entry provides is a typo that will read as a gap
  forever, sending someone to buy a part that does not exist under that name;
* a `capability` no registry part provides makes a project **unbuildable by
  construction** — the advisor will report it short of something nothing can
  satisfy, and the suggestion list will be empty.

Both fail silently in the advisor: they look like ordinary gaps. So they are
caught here instead.

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
        if has_part == has_cap:
            bad(f"{where}: needs exactly one of part_id or capability")
            continue
        if requirement.get("qty", 1) < 1:
            bad(f"{where}: qty must be >= 1")

        if has_part:
            part_id = requirement["part_id"]
            if not ID_RE.match(part_id):
                bad(f"{where}: malformed part_id '{part_id}'")
            elif part_id not in ids:
                bad(f"{where}: part_id '{part_id}' is not in the registry — "
                    "this reads as a permanent gap and sends someone shopping "
                    "for a part that does not exist under that name")
        else:
            capability = requirement["capability"]
            if capability not in capabilities:
                bad(f"{where}: capability '{capability}' is provided by no registry "
                    "part, so this project is unbuildable by construction")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parts", type=Path, default=ROOT.parent / "OpenPartsCore")
    parser.add_argument("--inventory", type=Path, default=ROOT / "example" / "inventory.json")
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

    for failure in failures:
        print(f"FAIL {failure}")
    print(
        f"{len(projects)} project(s) checked against {len(ids)} registry part(s) "
        f"and {len(capabilities)} capability token(s); "
        f"{'all valid' if not failures else str(len(failures)) + ' problem(s)'}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
