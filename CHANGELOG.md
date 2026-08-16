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
