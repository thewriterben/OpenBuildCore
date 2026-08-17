#!/usr/bin/env python3
"""Inventory-driven build advisor: what can I build, and what am I missing?

    python scripts/advisor.py what-can-i-build [--inventory F] [--parts DIR]
    python scripts/advisor.py gaps <project-id> [--inventory F] [--parts DIR]
    python scripts/advisor.py inventory [--inventory F] [--parts DIR]

A requirement is exactly one of three kinds:

* `part_id`     -- a specific part, which must resolve in OpenPartsCore
* `capability`  -- any part providing it will do
* `make`        -- a part to be FABRICATED rather than bought

The first two are a shopping question and share one exclusive allocation:
one unit of one part satisfies at most one requirement, so a single ESP32
cannot simultaneously be the camera node and the display node.

The third is a different question and gets a different answer. A project
short a LoRa radio can be fixed by buying one; a project needing a 260 mm
bracket on a 220 mm bed cannot be fixed by buying anything. So made parts
are judged against the machines you own (ADR-0005), reported separately, and
kept off the shopping list -- see ADR-0006.

Suggestions for a missing capability are found by *searching the registry*,
not from a hand-maintained list -- see DECISIONS.md ADR-0002.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import machines as machines_lib  # noqa: E402

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


def fabricate(req: dict, machines: list | None) -> dict:
    """Judge one made part against the machines the user owns.

    Kept apart from the shopping half on purpose. A project short a LoRa radio
    is a shopping problem; a project needing a 260 mm bracket on a 220 mm bed
    is not, and no amount of buying fixes it. Collapsing both into "missing"
    would put an unmakeable part on a shopping list, where it would sit
    unbought forever looking like an ordering oversight.

    No machines declared means UNKNOWN, not "cannot". The same rule as an
    undeclared scanner accuracy in OpenDesignCore: absence of evidence is
    recorded as absence, never as a negative finding.
    """
    record = {
        "make": req["make"],
        "size_mm": req["size_mm"],
        "material": req["material"],
        "qty": int(req.get("qty", 1)),
        "note": req.get("note", ""),
    }
    if machines is None:
        record["status"] = "unknown"
        record["reason"] = (
            "no machines declared - cannot say whether this can be made. "
            "Add machines.json, or see machines.py."
        )
        record["machines"] = []
        return record

    size = (req["size_mm"]["x"], req["size_mm"]["y"], req["size_mm"]["z"])
    verdicts = [
        machines_lib.evaluate(
            machine, size, req["material"], req.get("min_feature_mm"), None)
        for machine in machines
    ]
    capable = [v for v in verdicts if v["can_print"]]
    record["status"] = "makeable" if capable else "no_machine"
    record["machines"] = verdicts
    return record


def evaluate(project: dict, owned: dict, registry: dict,
             machines: list | None = None) -> dict:
    """Allocate owned parts to a project's requirements, exclusively.

    Specific-part requirements are settled first: they have exactly one way to
    be satisfied, so letting a capability requirement consume that stock first
    could report a false gap.

    Made parts are evaluated separately against `machines` and never enter the
    parts allocation or the shopping list - see fabricate().
    """
    remaining = dict(owned)
    satisfied, gaps, fabricated = [], [], []

    to_make = [r for r in project.get("requires", []) if r.get("make")]
    for req in to_make:
        fabricated.append(fabricate(req, machines))

    requirements = sorted(
        (r for r in project.get("requires", []) if not r.get("make")),
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

    # Two booleans, not one, because they fail differently and are fixed
    # differently: `buildable` is a shopping question, `makeable` is a
    # question about the machines in the room. A project with no made parts
    # is makeable vacuously; one with made parts and no declared machines is
    # None, which is "unknown" and is not treated as a failure.
    if not fabricated:
        makeable = True
    elif any(f["status"] == "unknown" for f in fabricated):
        makeable = None
    else:
        makeable = all(f["status"] == "makeable" for f in fabricated)

    return {
        "project": project["id"],
        "name": project["name"],
        "buildable": not gaps,
        "makeable": makeable,
        "satisfied": satisfied,
        "gaps": gaps,
        "fabricate": fabricated,
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


def shopping_list(results: list, simultaneous: bool) -> list:
    """Aggregate gaps across projects into one buyable list.

    Quantity depends on an assumption nobody should have to guess at:

    * sequential (default) -- you build these one at a time and reuse parts,
      so you need the *worst* single shortfall: max across projects.
    * simultaneous -- all of them exist at once, so shortfalls *sum*.

    Getting this wrong silently is how a shopping list under-orders.
    """
    needed: dict[str, dict] = {}
    for result in results:
        for gap in result["gaps"]:
            entry = needed.setdefault(
                gap["requirement"],
                {
                    "requirement": gap["requirement"],
                    "qty": 0,
                    "unlocks": [],
                    "suggestions": gap["suggestions"],
                },
            )
            entry["qty"] = (
                entry["qty"] + gap["qty_short"]
                if simultaneous
                else max(entry["qty"], gap["qty_short"])
            )
            entry["unlocks"].append(result["project"])
    return sorted(
        needed.values(), key=lambda e: (-len(e["unlocks"]), e["requirement"])
    )


def render_shopping(items: list, simultaneous: bool) -> None:
    basis = "all at once" if simultaneous else "one at a time"
    if not items:
        print("Nothing to buy: every project is buildable from stock.")
        return
    print(f"Shopping list (assuming you build them {basis}):\n")
    for item in items:
        unlocks = ", ".join(item["unlocks"])
        print(f"  {item['qty']:>3}x  {item['requirement']}")
        print(f"        unlocks: {unlocks}")
        for suggestion in item["suggestions"][:3]:
            print(f"        e.g. {suggestion['part_id']} - {suggestion['name']}")
        print()


def status_of(result: dict) -> str:
    """One label, but never one that hides which half failed."""
    if not result["buildable"]:
        return "MISSING PARTS" if result["makeable"] is not False else "BLOCKED"
    if result["makeable"] is False:
        return "NO MACHINE"
    if result["makeable"] is None:
        return "PARTS OK, MACHINES UNKNOWN"
    return "BUILDABLE"


def render(result: dict) -> None:
    print(f"[{status_of(result)}] {result['name']}  ({result['project']})")
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
    for made in result["fabricate"]:
        size = made["size_mm"]
        label = f"make:{made['make']}"
        dims = f"{size['x']} x {size['y']} x {size['z']} mm, {made['material']}"
        qty = f" x{made['qty']}" if made["qty"] > 1 else ""

        if made["status"] == "makeable":
            capable = [m for m in made["machines"] if m["can_print"]]
            print(f"    ok   {label:<34} {dims}{qty}")
            for verdict in capable[:2]:
                note = verdict["notes"][0] if verdict["notes"] else ""
                print(f"           {verdict['machine_id']} can make it - {note}")
        elif made["status"] == "unknown":
            print(f"    ?    {label:<34} {dims}{qty}")
            print(f"           {made['reason']}")
        else:
            print(f"    NO   {label:<34} {dims}{qty}")
            for verdict in made["machines"]:
                for blocker in verdict["blockers"]:
                    print(f"           {verdict['machine_id']}: {blocker}")
            print("           Not a shopping problem: no machine you own can "
                  "make this, so it is absent from the shopping list.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["what-can-i-build", "gaps", "inventory", "shopping-list"],
    )
    parser.add_argument("project", nargs="?", default=None)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--parts", type=Path, default=DEFAULT_PARTS)
    parser.add_argument(
        "--machines", type=Path, default=machines_lib.DEFAULT_MACHINES,
        help="machines you own; made parts are checked against these. Absent "
             "means made parts report 'unknown', never 'cannot'.",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--for", dest="for_projects", default=None,
        help="comma-separated project ids to shop for (default: all)",
    )
    parser.add_argument(
        "--simultaneous", action="store_true",
        help="you want all the projects to exist at once, so shortfalls sum "
             "instead of being reused across sequential builds",
    )
    args = parser.parse_args()

    registry = load_registry(args.parts)
    owned = load_inventory(args.inventory, registry)
    projects = load_projects(ROOT / "data" / "projects")
    machines = (machines_lib.load_machines(args.machines)
                if args.machines.exists() else None)

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
        result = evaluate(match, owned, registry, machines)
        print(json.dumps(result, indent=2) if args.json else "", end="")
        if not args.json:
            render(result)
        # Unknown does not fail: absence of declared machines is not a finding.
        return 0 if result["buildable"] and result["makeable"] is not False else 1

    if args.command == "shopping-list":
        chosen = projects
        if args.for_projects:
            wanted = {p.strip() for p in args.for_projects.split(",")}
            chosen = [p for p in projects if p["id"] in wanted]
            unknown = wanted - {p["id"] for p in chosen}
            if unknown:
                print(f"unknown project(s): {', '.join(sorted(unknown))}", file=sys.stderr)
                return 2
        results = [evaluate(p, owned, registry, machines) for p in chosen]
        items = shopping_list(results, args.simultaneous)
        if args.json:
            print(json.dumps(
                {"basis": "simultaneous" if args.simultaneous else "sequential",
                 "items": items}, indent=2))
        else:
            render_shopping(items, args.simultaneous)
        return 0

    results = [evaluate(p, owned, registry, machines) for p in projects]
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    ready = [r for r in results if r["buildable"] and r["makeable"] is not False]
    blocked = [r for r in results if r not in ready]
    for result in ready + blocked:
        render(result)
        print()

    print(f"{len(ready)} of {len(results)} project(s) ready from this inventory.")
    stuck = [r for r in results if r["buildable"] and r["makeable"] is False]
    if stuck:
        # Said separately because the fix is different in kind: these are not
        # short a part anyone sells.
        print(f"{len(stuck)} have every part but no machine that can make "
              "their custom pieces: " + ", ".join(r["project"] for r in stuck))
    if machines is None and any(r["fabricate"] for r in results):
        print("No machines declared, so parts to be made are reported as "
              "unknown rather than judged. See example/machines.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
