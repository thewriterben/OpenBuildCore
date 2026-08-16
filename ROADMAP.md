# Roadmap

## Now
- [x] Advisor: quantity-aware exclusive allocation, registry-derived suggestions, 8 tests (2026-08-15)
- [x] Three seed projects exercising the interesting cases (buildable, part-short, capability-short)
- [ ] JSON Schema files for inventory and project documents, plus a validator like OpenPartsCore's
- [ ] Grow the project catalogue past the point where "what can I build" is interesting

## Next
- [x] Shopping list: gaps → one buyable list, deduplicated across projects, with an explicit sequential/simultaneous basis (ADR-0004) (2026-08-15)
- [ ] Live pricing on the shopping list, keyed by part id (distributor APIs)
- [ ] MCP surface, following OpenDesignCore ADR-0009: reads and matching execute, nothing here reaches a fabricator
- [ ] "What should I build?" ranking — order buildable projects by how much of the inventory they use, or by fewest missing parts
- [ ] Inventory capture assist: photograph a drawer, identify parts (ClawCam-adjacent vision already exists in the ecosystem)

## Not yet
- Backtracking allocation (see ADR-0002 — greedy is honest but not optimal)
- Project dependency graphs (project A produces a part used by project B)
- Multi-owner or shared inventories

## Not ever
- Part facts. Those belong in OpenPartsCore with citations.
- Pricing and stock. Live from distributors, keyed by part id.
- Claiming a project is buildable without accounting for quantities.
