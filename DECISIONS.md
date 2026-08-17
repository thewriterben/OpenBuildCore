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

---

## ADR-0004 — A shopping list must state whether builds are sequential or simultaneous

**Date:** 2026-08-15
**Status:** accepted

**Context.** Aggregating gaps across projects into one buyable list needs a quantity per line, and there are two defensible answers. If you build projects one at a time, parts are reused, so you need the **worst single shortfall** — the max. If all the projects must exist at once, shortfalls **sum**. With the seed catalogue the answers differ: `two-node-mesh` needs 2 LoRa radios and `lora-relay` needs 1, giving **2 sequentially and 3 simultaneously**.

Picking one silently is how a shopping list under-orders — and under-ordering is discovered at the bench, after the parts arrive.

**Decision.** Sequential is the default, because building one thing at a time is the common case and it is the cheaper of the two errors to correct. `--simultaneous` sums. The chosen basis is printed in the human output and carried as a `basis` field in `--json`, so a consumer never has to infer it.

**Consequences.** One more flag, and a real distinction made explicit rather than assumed. The default can still be wrong for someone assembling a fleet — but they are told which assumption produced their list, which is the difference between a wrong number and an unexplained one. Neither mode models parts that are consumed destructively; that would be a third basis, and there is no case for it yet.

---

## ADR-0005 — Machines are owned state, and print time is never modelled

**Date:** 2026-08-16
**Status:** accepted

**Context.** "What can I build" has a second half the advisor could not answer: whether the user can actually *make* the physical parts. A project that needs a 260 mm bracket is not buildable on a 220 mm bed, and no amount of inventory matching will say so. So machines needed a home.

Two questions had to be answered before writing anything.

**Where machines live.** Machines are exactly like inventory: a record of physical objects a particular person owns, mutable, personal, and meaningless to anyone else. By ADR-0001's reasoning they belong here rather than in the cited reference registry, and `machines.json` is git-ignored the same way `inventory.json` is, with `example/machines.json` shipped as the template. Field names follow Project BINGO's machine record (`machine_id`, `driver`, `make`/`model`, `process`, `envelope_mm`, `materials`, `tier`) so that a machine described here can be handed to a BINGO node without translation.

**How print time is answered.** This is the decision with teeth. A volumetric estimate — part volume over an assumed extrusion rate — is easy, and is what most tools do. It is also a number with no provenance: it ignores travel, infill pattern, supports, cooling and acceleration limits, it is wrong by factors rather than percentages on anything but a solid block, and once printed it will be read as a measurement. That is precisely the failure mode the "never invent physical data" invariant exists to prevent, applied to a derived quantity instead of a datasheet value.

**Decision.**

- A time estimate is produced **only** when the machine record carries a `measured_throughput` its owner measured, and only when `how_measured` says how. The validator rejects a rate without one, because an unsourced rate is indistinguishable from a recalled one.
- Machines without a measured throughput answer **"requires slicing"**. Absence of an estimate is the honest default, not a gap to be filled.
- Even a measured estimate is labelled pre-slicing triage that a slicer supersedes, and the caveat travels in the returned result rather than in documentation.
- Fit is checked over all six **axis-aligned** orientations and the working one is named, because a part that fails flat often fits stood on end. Arbitrary orientations are out of scope and stated as such: finding them is a slicer's or a human's job.
- Every machine needs a `source.citation`, the same gate the reference registry uses. A capability is a physical claim about hardware.

**Consequences.** The system will frequently answer "I cannot tell you how long this takes", which is less useful than a number and more useful than a wrong one. Users who want estimates have a clear path: time one print, record the rate and the method. The shipped K2 Plus record demonstrates the discipline uncomfortably — its `envelope_mm` is a `1×1×1` placeholder marked `TODO(source)` because the build volume is not in the cited material, so every fit check on it fails loudly rather than passing on a guessed number. That is the intended behaviour, and a test pins it.

Axis-aligned-only fit will report false negatives on parts that need a diagonal. That is the safe direction to be wrong in, and the message says which check failed so a human can overrule it.

---

## ADR-0006 — Parts to be made are a third kind of requirement, not a part nobody sells

**Date:** 2026-08-16
**Status:** accepted (completes ADR-0005)

**Context.** ADR-0005 gave machines a model but left them beside the advisor rather than inside it: `machines.py` answered "can this be printed" about a size you typed, and `advisor.py` answered "can I build this" about parts you own. Neither could answer the actual question, which is whether you can finish the thing. Most real builds need a bracket, a case, a mount — parts nobody sells, that you make.

The cheap option was to model a made part as a `part_id` under some `mechanical/` namespace and let the existing gap machinery handle it. That is wrong in a specific and expensive way.

**A missing part and an unmakeable part fail differently and are fixed differently.** Short a LoRa radio? Buy one. Need a 260 mm stake on a 220 mm bed? Nothing you can buy fixes that — you redesign it, split it, or use a different machine. Collapsing both into "missing" would put an unmakeable part onto a shopping list, where it would sit unbought forever looking like an ordering oversight rather than a design problem.

**Decision.** A requirement is exactly one of three kinds: `part_id`, `capability`, or `make`. A `make` requirement carries `size_mm`, `material`, an optional `min_feature_mm`, and a quantity.

- Made parts are judged against the user's machines (ADR-0005) and reported under `fabricate`, **never** under `gaps`, so they cannot reach the shopping list.
- They take no part in the exclusive allocation. A fabricated bracket must not compete with the electronics for the one board in the drawer.
- A result carries **two** booleans, `buildable` and `makeable`, because one label cannot say which half failed and the two halves have different remedies. The rendered status names it: `BUILDABLE`, `MISSING PARTS`, `NO MACHINE`, `BLOCKED`, `PARTS OK, MACHINES UNKNOWN`.
- **No machines declared means `makeable: null` — unknown, not false.** The same rule as OpenDesignCore's undeclared scanner accuracy: absence of evidence is recorded as absence and never as a negative finding. `gaps` exits non-zero for `false` and zero for `null`.
- The validator checks a made part's **shape only** and never against owned machines. Projects are shareable; machines are personal. A project needing ASA is perfectly valid for someone with no ASA-capable printer — that is a capability gap the advisor reports, not an error in the file. Validating against machines would make a project's validity depend on who is reading it.
- `material` is required. A made part without one cannot be checked against a machine at all, and defaulting to PLA would be inventing a design decision on the author's behalf.

**Consequences.** "What can I build" finally answers the whole question, and answers it honestly in the case that used to be invisible: you own every component and still cannot finish, because the part you have to make will not fit anything you own. The seed catalogue now exercises both outcomes — `env-monitor`'s desk case is makeable on the example bench machine, `soil-moisture-nodes`' 260 mm probe stake is not, and `bird-feeder-cam`'s ASA housing fails on material rather than size. A test asserts both a `makeable` and a `no_machine` appear in shipped data, so the negative path cannot quietly stop being exercised.

`size_mm` in a project file is a design *intent* declared by the author, not a measurement. Real dimensions come from an OpenDesignCore provenance record, which `machines.py can-print --from-sidecar` reads directly. The project figure is what you check *before* you have a design; the sidecar is what you check after. Keeping both is deliberate, and the project files say so.

Three requirement kinds is the ceiling. A fourth — "salvage from something you own", say — would need its own ADR and a real case, not a guess that someone might want it.
