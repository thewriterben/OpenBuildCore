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


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
