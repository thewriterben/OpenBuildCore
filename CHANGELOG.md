# Changelog

## [Unreleased]
### Added
- Repo created as the platform's fourth peer (ADR-0001): inventory + ideation, separate from the cited parts registry per PD-2.
- `scripts/advisor.py`: `what-can-i-build`, `gaps <project>`, `inventory`, all with `--json`. Requirements are specific parts or capabilities, each with a quantity; allocation is exclusive, so one unit satisfies at most one requirement. Suggestions are found by searching OpenPartsCore rather than from hardcoded lists (ADR-0002).
- Three seed projects — `env-monitor` (buildable), `camera-trap` (buildable), `two-node-mesh` (short two LoRa radios) — chosen to exercise buildable, part-short and capability-short cases.
- Example inventory of 6 part types; unresolvable part ids are refused outright.
- 8 tests (stdlib unittest) pinning exclusive allocation, quantity accounting, specific-before-capability ordering, and registry-derived suggestions.
- `shopping-list` command: gaps across projects aggregated into one buyable list, sorted by how many projects each item unlocks. Quantity basis is **explicit** (ADR-0004) — sequential by default (parts reused between builds, quantity = max shortfall), `--simultaneous` to sum. On the seed catalogue that is 2 vs 3 LoRa radios. `--for a,b` narrows to chosen projects; `--json` carries the basis so a consumer never infers it.
- Fourth seed project `lora-relay`, chosen so the sequential/simultaneous difference is visible rather than theoretical.
- 12 tests (up from 8), including all four shopping-list behaviours.
- obc_mcp: stdio MCP surface exposing inventory, list_projects, what_can_i_build, gaps and shopping_list. All five execute - nothing here writes to a store or reaches a fabricator (OpenDesignCore ADR-0009). Deliberately no tool edits inventory: an agent quietly changing what you own would poison every answer downstream. Verified connected against a real MCP client.
- Written against MCP Python SDK 2.x, where MCPServer replaced FastMCP; mcp.server.fastmcp no longer exists. Package named obc_mcp so it cannot shadow the SDK.
- JSON Schemas for project and inventory documents, plus scripts/validate.py. Structure is the easy half; the half that matters is referential integrity: a part_id no registry entry provides reads as a permanent gap and sends someone shopping for a name that does not exist, and a capability no part provides makes a project unbuildable by construction with an empty suggestion list. Both look like ordinary gaps in the advisor, so they are caught here.
- Catalogue grown 4 -> 8 projects (desk-air-quality, macro-keypad, bird-feeder-cam, soil-moisture-nodes), spanning beginner to advanced and using only capability tokens the registry actually provides. The example inventory now builds 3 of 8, which is a realistic ratio and makes the shopping list worth reading: one wifi board unlocks three projects.
- 21 tests (up from 12). Nine are negative cases proving the validator rejects what it should - a validator that never rejects anything reports 'all valid' forever (OpenCircuitCore ADR-0006's lesson).
