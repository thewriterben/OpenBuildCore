#!/usr/bin/env python3
"""Inventory-driven build advisor: what can I build, and what am I missing?

    python scripts/advisor.py what-can-i-build [--inventory F] [--parts DIR]
    python scripts/advisor.py gaps <project-id> [--inventory F] [--parts DIR]
    python scripts/advisor.py inventory [--inventory F] [--parts DIR]

Requirements are either a specific part (`part_id`) or a capability any part
may provide (`capability`), each with a quantity. Allocation is exclusive:
one unit of one part satisfies at most one requirement, so a single ESP32
cannot simultaneously be the camera node and the display node.

Suggestions for a missing capability are found by *searching the registry*,
not from a hand-maintained list -- see DECISIONS.md ADR-0002.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PARTS = ROOT.parent / "OpenPartsCore"
DEFAULT_INVENTORY = ROOT / "example" / "inventory.json"


def load_registry(parts_dir: Path) -> dict:
    data_dir = parts_dir / "data"
    if not data_dir.exists():
        raise SystemExit(
            f"OpenPartsCore data not found at {data_dir}. Pass --parts <dir>."
        )
    registry = {}
    for path in sorted(data_dir.rglob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        registry[entry["id"]] = entry
    return registry


def capabilities_of(entry: dict) -> set[str]:
    return set((entry.get("attributes") or {}).get("capabilities") or [])


def load_inventory(path: Path, registry: dict) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    owned: dict[str, int] = {}
    unknown = []
    for item in doc.get("items", []):
        part_id = item["part_id"]
        if part_id not in registry:
            unknown.append(part_id)
            continue
        owned[part_id] = owned.get(part_id, 0) + int(item.get("qty", 1))
    if unknown:
        raise SystemExit(
            "Inventory references parts that are not in the registry: "
            + ", ".join(sorted(unknown))
            + "\nAdd them to OpenPartsCore (with a citation) before claiming to own them."
        )
    return owned


def load_projects(projects_dir: Path) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(projects_dir.glob("*.json"))
    ]


def evaluate(project: dict, owned: dict, registry: dict) -> dict:
    """Allocate owned parts to a project's requirements, exclusively.

    Specific-part requirements are settled first: they have exactly one way to
    be satisfied, so letting a capability requirement consume that stock first
    could report a false gap.
    """
    remaining = dict(owned)
    satisfied, gaps = [], []

    requirements = sorted(
        project.get("requires", []),
        key=lambda r: 0 if r.get("part_id") else 1,
    )

    for req in requirements:
        need = int(req.get("qty", 1))
        label = req.get("part_id") or f"capability:{req['capability']}"
        allocated: list[tuple[str, int]] = []

        if req.get("part_id"):
            candidates = [req["part_id"]] if req["part_id"] in remaining else []
        else:
            cap = req["capability"]
            candidates = sorted(
                pid for pid in remaining
                if cap in capabilities_of(registry[pid])
            )

        for pid in candidates:
            if need == 0:
                break
            take = min(need, remaining.get(pid, 0))
            if take:
                allocated.append((pid, take))
                remaining[pid] -= take
                need -= take

        record = {
            "requirement": label,
            "note": req.get("note", ""),
            "qty_required": int(req.get("qty", 1)),
            "allocated": [{"part_id": p, "qty": q} for p, q in allocated],
        }
        if need == 0:
            satisfied.append(record)
        else:
            record["qty_short"] = need
            record["suggestions"] = suggest(req, registry, owned)
            gaps.append(record)

    return {
        "project": project["id"],
        "name": project["name"],
        "buildable": not gaps,
        "satisfied": satisfied,
        "gaps": gaps,
    }


def suggest(req: dict, registry: dict, owned: dict) -> list[dict]:
    """Registry-derived suggestions. No hand-maintained lists."""
    if req.get("part_id"):
        entry = registry.get(req["part_id"])
        return [{
            "part_id": req["part_id"],
            "name": entry["name"] if entry else "(not in registry)",
        }]
    cap = req["capability"]
    found = [
        {"part_id": pid, "name": entry["name"]}
        for pid, entry in sorted(registry.items())
        if cap in capabilities_of(entry) and pid not in owned
    ]
    return found[:5]


def render(result: dict) -> None:
    mark = "BUILDABLE" if result["buildable"] else "MISSING PARTS"
    print(f"[{mark}] {result['name']}  ({result['project']})")
    for item in result["satisfied"]:
        using = ", ".join(f"{a['qty']}x {a['part_id']}" for a in item["allocated"])
        print(f"    ok   {item['requirement']:<34} <- {using}")
    for gap in result["gaps"]:
        have = sum(a["qty"] for a in gap["allocated"])
        print(
            f"    NEED {gap['requirement']:<34} "
            f"short {gap['qty_short']} of {gap['qty_required']} (have {have})"
        )
        for suggestion in gap["suggestions"]:
            print(f"           consider {suggestion['part_id']} - {suggestion['name']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["what-can-i-build", "gaps", "inventory"])
    parser.add_argument("project", nargs="?", default=None)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--parts", type=Path, default=DEFAULT_PARTS)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    registry = load_registry(args.parts)
    owned = load_inventory(args.inventory, registry)
    projects = load_projects(ROOT / "data" / "projects")

    if args.command == "inventory":
        payload = [
            {"part_id": pid, "qty": qty, "name": registry[pid]["name"],
             "capabilities": sorted(capabilities_of(registry[pid]))}
            for pid, qty in sorted(owned.items())
        ]
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for item in payload:
                caps = ", ".join(item["capabilities"]) or "-"
                print(f"  {item['qty']:>3}x {item['part_id']:<28} {item['name']}")
                print(f"       capabilities: {caps}")
        return 0

    if args.command == "gaps":
        if not args.project:
            print("gaps needs a project id", file=sys.stderr)
            return 2
        match = next((p for p in projects if p["id"] == args.project), None)
        if match is None:
            print(f"unknown project '{args.project}'. Known: "
                  + ", ".join(p["id"] for p in projects), file=sys.stderr)
            return 2
        result = evaluate(match, owned, registry)
        print(json.dumps(result, indent=2) if args.json else "", end="")
        if not args.json:
            render(result)
        return 0 if result["buildable"] else 1

    results = [evaluate(p, owned, registry) for p in projects]
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    buildable = [r for r in results if r["buildable"]]
    blocked = [r for r in results if not r["buildable"]]
    for result in buildable + blocked:
        render(result)
        print()
    print(f"{len(buildable)} of {len(results)} project(s) buildable from this inventory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
