"""OpenBuildCore stdio MCP server.

Exposes the build advisor to any MCP client, so an agent can answer "what can
I build with what I own" without shelling out to the CLI.

Every tool here **reads**. Nothing in this repo writes to a store, moves
hardware, or reaches a fabricator, so OpenDesignCore ADR-0009's execute-vs-
propose line puts all of it on the execute side. There is deliberately **no
tool that edits inventory**: inventory is the user's own record of physical
objects, and an agent quietly deciding you own three more resistors than you
do would poison every answer downstream.

The package is named `obc_mcp`, not `mcp`, because the latter shadows the SDK.

Run:
    python -m obc_mcp.server
    OBC_INVENTORY=<file> OPC_DIR=<dir> python -m obc_mcp.server

Requires:  pip install -r obc_mcp/requirements.txt
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import advisor  # noqa: E402
import machines as machines_lib  # noqa: E402

try:
    # SDK 2.x. `mcp.server.fastmcp` was the 1.x entry point and no longer
    # exists -- AdvancedStudio's studio-mcp still imports it and is broken
    # against 2.0 on this machine. Reported in the platform wiki.
    from mcp.server import MCPServer
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing or too-old dependency. Run: pip install -r obc_mcp/requirements.txt"
    ) from exc

server = MCPServer("openbuildcore")


def _load():
    inventory_path = Path(os.getenv("OBC_INVENTORY", str(advisor.DEFAULT_INVENTORY)))
    parts_dir = Path(os.getenv("OPC_DIR", str(advisor.DEFAULT_PARTS)))
    registry = advisor.load_registry(parts_dir)
    owned = advisor.load_inventory(inventory_path, registry)
    projects = advisor.load_projects(ROOT / "data" / "projects")
    return registry, owned, projects


@server.tool()
def inventory() -> list:
    """What the user owns: part ids, quantities, names and capabilities.

    Read-only. This server cannot change inventory; a person edits the file.
    """
    registry, owned, _ = _load()
    return [
        {
            "part_id": part_id,
            "qty": qty,
            "name": registry[part_id]["name"],
            "capabilities": sorted(advisor.capabilities_of(registry[part_id])),
        }
        for part_id, qty in sorted(owned.items())
    ]


@server.tool()
def list_projects() -> list:
    """Every known project, with its requirements and difficulty."""
    _, _, projects = _load()
    return [
        {
            "id": project["id"],
            "name": project["name"],
            "description": project.get("description", ""),
            "difficulty": project.get("difficulty", ""),
            "requires": project.get("requires", []),
        }
        for project in projects
    ]


@server.tool()
def what_can_i_build() -> list:
    """Evaluate every project against the inventory.

    Allocation is exclusive: one unit of one part satisfies at most one
    requirement, so a single board cannot be both nodes of a two-node mesh.
    """
    registry, owned, projects = _load()
    return [advisor.evaluate(project, owned, registry) for project in projects]


@server.tool()
def gaps(project_id: str) -> dict:
    """What a specific project is missing, with registry-derived suggestions."""
    registry, owned, projects = _load()
    match = next((p for p in projects if p["id"] == project_id), None)
    if match is None:
        known = ", ".join(p["id"] for p in projects)
        raise ValueError(f"unknown project '{project_id}'. Known: {known}")
    return advisor.evaluate(match, owned, registry)


@server.tool()
def shopping_list(project_ids: str = "", simultaneous: bool = False) -> dict:
    """Aggregate gaps into one buyable list.

    `simultaneous` decides the quantity and is never guessed at: sequential
    builds reuse parts so the quantity is the worst single shortfall, while
    simultaneous builds sum. The basis is returned so a caller never has to
    infer which question was answered.
    """
    registry, owned, projects = _load()
    chosen = projects
    if project_ids.strip():
        wanted = {p.strip() for p in project_ids.split(",") if p.strip()}
        chosen = [p for p in projects if p["id"] in wanted]
        unknown = wanted - {p["id"] for p in chosen}
        if unknown:
            raise ValueError(f"unknown project(s): {', '.join(sorted(unknown))}")

    results = [advisor.evaluate(project, owned, registry) for project in chosen]
    return {
        "basis": "simultaneous" if simultaneous else "sequential",
        "items": advisor.shopping_list(results, simultaneous),
    }


def _machines():
    path = Path(os.getenv("OBC_MACHINES", str(machines_lib.DEFAULT_MACHINES)))
    return machines_lib.load_machines(path)


@server.tool()
def list_machines() -> list:
    """The machines the user owns, with envelope, materials and constraints.

    Read-only, like inventory: an agent inventing a build volume it did not
    measure is the same failure as inventing a component you do not own.
    """
    return _machines()


@server.tool()
def can_print(
    size_mm: str,
    material: str = "",
    min_feature_mm: float = 0.0,
    volume_mm3: float = 0.0,
) -> list:
    """Which machines can make a part this size, and what stops the others.

    `size_mm` is the bounding box as "XxYxZ" in millimetres. Fit is tried in
    all six axis-aligned orientations and the one that works is named.

    A time estimate appears only when the machine carries a throughput its
    owner measured, and even then it is pre-slicing triage that a slicer
    supersedes. Machines without one answer "requires slicing" rather than
    returning a modelled number with no provenance.
    """
    part = machines_lib.parse_size(size_mm)
    return [
        machines_lib.evaluate(
            machine,
            part,
            material or None,
            min_feature_mm or None,
            volume_mm3 or None,
        )
        for machine in _machines()
    ]


@server.tool()
def can_print_design(
    sidecar_path: str,
    material: str = "",
    min_feature_mm: float = 0.0,
) -> dict:
    """Judge an OpenDesignCore design against the user's machines.

    `sidecar_path` points at a `.provenance.json` record. Size and volume come
    from the record's `artifact.bbox_mm` and `volume_cubic_mm`, so the answer
    is about the geometry that will actually be printed and can name the
    artifact hash it judged.

    A record too old to carry those fields is refused with its schema named,
    rather than falling back to the part envelope - which is the thing that
    goes *inside* the enclosure, not the thing that gets printed, and would be
    wrong by twice the clearance plus twice the wall while looking plausible.

    Material is not read from the record: OpenDesignCore designs geometry and
    does not know what it will be printed in.
    """
    source = machines_lib.load_sidecar(Path(sidecar_path))
    return {
        "source": source,
        "machines": [
            machines_lib.evaluate(
                machine,
                source["size_mm"],
                material or None,
                min_feature_mm or None,
                source["volume_mm3"],
            )
            for machine in _machines()
        ],
    }


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
