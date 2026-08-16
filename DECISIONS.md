# Decisions

Append-only. Newest at the bottom.

---

## ADR-0001 — A separate repo for inventory and ideation

**Date:** 2026-08-15
**Status:** accepted (extends platform decisions PD-2/PD-3, recorded in OpenDesignCore `wiki/concepts/platform-decisions.md`)

**Context.** PD-2 established that user inventory is mutable state referencing canonical part ids, deliberately not part of the cited reference registry. It did not say where inventory lives. Three candidates: inside OpenPartsCore, folded into Oh-Ben-Claw's deployment-generator (which already matches inventory to agent deployments), or its own peer.

**Decision.** Its own repo, a fourth Open*Core peer under ADR-0007's engine-among-peers shape.

**Consequences.** Reference data stays reviewable and citation-gated while inventory stays mutable and personal — the separation PD-2 asked for is structural rather than a convention. Oh-Ben-Claw's planner keeps its agent-deployment specialisation and its parity-fixtured config generation; this repo takes the general case. A fourth repo is a real maintenance cost, justified by the fact that inventory has a different lifecycle, different privacy posture, and different consumers from everything else.

---

## ADR-0002 — Quantity-aware exclusive allocation, and registry-derived suggestions

**Date:** 2026-08-15
**Status:** accepted

**Context.** Oh-Ben-Claw's `planDeployment` is the working prior art and was read closely before writing anything here. Its core is sound: capability tokens unioned across a board and its accessories, with desires expressed as all-of/any-of capability sets. Three properties of it do not survive generalisation beyond agent deployments:

1. **Presence-only matching.** Every check is `.length > 0` or `[0]`. A project needing two hosts is reported satisfiable by one board.
2. **No exclusivity.** Aside from one ad-hoc filter, a single item can satisfy several roles at once.
3. **Hardcoded suggestions.** Missing-hardware advice is literal string arrays in the function body; the registry is never searched, so suggestions go stale as the registry grows.

**Decision.**

- Requirements carry a **quantity**, and matching allocates stock **exclusively** — one unit satisfies at most one requirement. Shortfalls are reported as "short N of M", not as a boolean.
- Specific-part requirements are allocated **before** capability requirements, since a specific part has exactly one way to be satisfied and a capability requirement would otherwise consume its only unit and report a false gap.
- Suggestions are computed by **querying the registry** for parts providing the missing capability, excluding parts already owned.

**Consequences.** Results are honest about the case that matters most to someone standing at a parts drawer: not "can this be built in principle" but "can *I* build it with what is in front of me". Greedy allocation is not optimal — a pathological case could allocate a versatile part to a requirement a cheaper part could have filled, and report a false gap. Backtracking would fix it and is not worth the complexity until a real project exposes it; when one does, it belongs in a superseding ADR rather than a quiet rewrite.

---

## ADR-0003 — Apache-2.0

**Date:** 2026-08-15
**Status:** accepted (PD-4)

Uniform with OpenDesignCore, OpenPartsCore and OpenCircuitCore.
