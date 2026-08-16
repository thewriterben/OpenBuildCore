# Roadmap

## Now
- [x] Advisor: quantity-aware exclusive allocation, registry-derived suggestions, 8 tests (2026-08-15)
- [x] Three seed projects exercising the interesting cases (buildable, part-short, capability-short) (2026-08-15)
- [x] JSON Schema files for inventory and project documents, plus a validator like OpenPartsCore's — nine negative tests prove it rejects (2026-08-15)
- [x] Grow the project catalogue past the point where "what can I build" is interesting — 8 projects, of which the example inventory builds 3 (2026-08-15)
- [x] Machines: owned state alongside inventory, with fit / material / feature-size / time answered per machine. Time only from a measured throughput; everything else answers "requires slicing" (ADR-0005) (2026-08-16)

## Next
- [x] Shopping list: gaps -> one buyable list, deduplicated across projects, with an explicit sequential/simultaneous basis (ADR-0004) (2026-08-15)
- [x] MCP surface, following OpenDesignCore ADR-0009: reads and matching execute, nothing here reaches a fabricator (2026-08-15)
- [ ] **Replace the K2 Plus placeholder envelope.** `envelope_mm` is `1x1x1` and marked `TODO(source)`; every fit check on that machine fails until someone measures the bed or cites the manual.
- [x] Take a part's bounding box from an OpenDesignCore artifact rather than a `--size` string typed by hand — `can-print --from-sidecar` reads `artifact.bbox_mm` and `volume_cubic_mm` (ODC ADR-0010); the peers meet at the provenance record, not at an API (2026-08-16)
- [ ] Projects declare the parts they need *made*, not only bought, so `what-can-i-build` can consult machines instead of leaving the physical half unanswered
- [ ] Live pricing on the shopping list, keyed by part id (distributor APIs)
- [ ] "What should I build?" ranking — order buildable projects by how much of the inventory they use, or by fewest missing parts
- [ ] Inventory capture assist: photograph a drawer, identify parts (ClawCam-adjacent vision already exists in the ecosystem)

## Not yet
- Backtracking allocation (see ADR-0002 — greedy is honest but not optimal)
- Non-axis-aligned fit. Six orientations will report false negatives on parts needing a diagonal; overruling that is a slicer's or a human's job for now (ADR-0005).
- Machine capabilities beyond FDM: resin, CNC and laser have constraints this model does not carry. Add them when a real machine needs them, not before.
- Project dependency graphs (project A produces a part used by project B)
- Multi-owner or shared inventories

## Not ever
- Part facts. Those belong in OpenPartsCore with citations.
- Pricing and stock. Live from distributors, keyed by part id.
- Claiming a project is buildable without accounting for quantities.
- Slicing. Toolpaths, supports and true print time belong to a slicer; this repo does pre-slicing triage and says so.
- A modelled print time. If nobody measured it, the answer is "requires slicing" (ADR-0005).
