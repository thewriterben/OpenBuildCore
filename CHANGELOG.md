# Changelog

## [Unreleased]
### Added
- Repo created as the platform's fourth peer (ADR-0001): inventory + ideation, separate from the cited parts registry per PD-2.
- `scripts/advisor.py`: `what-can-i-build`, `gaps <project>`, `inventory`, all with `--json`. Requirements are specific parts or capabilities, each with a quantity; allocation is exclusive, so one unit satisfies at most one requirement. Suggestions are found by searching OpenPartsCore rather than from hardcoded lists (ADR-0002).
- Three seed projects — `env-monitor` (buildable), `camera-trap` (buildable), `two-node-mesh` (short two LoRa radios) — chosen to exercise buildable, part-short and capability-short cases.
- Example inventory of 6 part types; unresolvable part ids are refused outright.
- 8 tests (stdlib unittest) pinning exclusive allocation, quantity accounting, specific-before-capability ordering, and registry-derived suggestions.
