# OpenBuildCore

Tell it what you own. It tells you what you can build, and exactly what you're missing.

**Status:** pre-alpha. The matcher works; the project catalogue is three entries deep.

## Try it

```
python scripts/advisor.py what-can-i-build
```

```
[BUILDABLE] Environmental monitor with local display  (env-monitor)
    ok   electronic/bme280                  <- 1x electronic/bme280
    ok   capability:gpio                    <- 1x boards/esp32-s3

[MISSING PARTS] Two-node sensor mesh  (two-node-mesh)
    ok   capability:gpio                    <- 2x boards/esp32-s3
    NEED capability:lora                    short 2 of 2 (have 0)
           consider boards/heltec-wifi-lora-32-v3 - heltec-wifi-lora-32-v3
           consider boards/lilygo-t-beam - lilygo-t-beam
```

Then buy the right things:

```
python scripts/advisor.py shopping-list
```

```
Shopping list (assuming you build them one at a time):

    2x  capability:lora
        unlocks: lora-relay, two-node-mesh
        e.g. boards/heltec-wifi-lora-32-v3 - heltec-wifi-lora-32-v3
```

`--simultaneous` if you want them all to exist at once — then the same list says **3x**, because shortfalls sum instead of parts being reused between builds. The basis is always stated, never assumed (ADR-0004). `--for a,b` shops for chosen projects only.

Also: `advisor.py inventory`, `advisor.py gaps <project-id>`, and `--json` on any command.

### And whether you can actually make the parts

```
python scripts/machines.py can-print --size 40x30x12 --material petg --volume-mm3 9000
```

```
[CANNOT] Creality K2 Plus  (k2-plus)
    NO   does not fit: part 40.0 x 30.0 x 12.0 mm vs envelope 1 x 1 x 1 mm, in any axis-aligned orientation
    time unknown: no measured throughput on this machine - print time requires slicing

[CAN PRINT] Example Bench FDM  (example-bench-fdm)
    ok   fits as modelled (40.0 x 30.0 x 12.0 mm)
    time ~0.6 h - pre-slicing triage only: bulk volume over one measured rate, ...
```

That first result is the design working, not failing. The K2 Plus record's build
volume is a `1x1x1` placeholder marked `TODO(source)` because it isn't in the
cited material, so every fit check on it fails loudly rather than passing on a
guessed number. Fill in a measured envelope and it starts answering.

**Print time is never modelled.** A machine gets a time estimate only if its
record carries a throughput its owner measured and says how they measured it.
Everything else answers "requires slicing", because a volumetric guess is a
number with no provenance and would be read as a measurement (ADR-0005).

Fit is tried in all six axis-aligned orientations and the one that works is
named — a part that fails flat often fits stood on end. `machines.py list`
shows what you own.

## How it works

- **Inventory** (`example/inventory.json`) is a list of `part_id` + `qty`. Every id must exist in [OpenPartsCore](https://github.com/thewriterben/OpenPartsCore) — inventory that can't be resolved is refused rather than half-understood.
- **Projects** (`data/projects/*.json`) declare requirements as either a specific `part_id` or a `capability` any part may provide, each with a quantity.
- **Matching** allocates owned stock to requirements **exclusively**: one unit satisfies at most one requirement. A single ESP32 cannot be both nodes of a two-node mesh.
- **Suggestions** for a missing capability are found by **searching the registry**, so they improve as the registry grows. No hand-maintained lists.
- **Machines** (`example/machines.json`) are owned state like inventory, with fields named to match Project BINGO's machine record so one can be handed to a node without translation. Every capability needs a citation; a throughput needs a `how_measured`.

`python scripts/validate.py` checks all three, and refuses a machine whose rate has no method attached.

## Where it sits

Fourth peer in the platform (OpenDesignCore ADR-0007):

| | |
|---|---|
| [OpenPartsCore](https://github.com/thewriterben/OpenPartsCore) | what parts *are* — cited reference data |
| **OpenBuildCore** | what you *have*, and what you could make of it |
| [OpenCircuitCore](https://github.com/thewriterben/OpenCircuitCore) | electronics design for the thing you decided to build |
| [OpenDesignCore](https://github.com/thewriterben/OpenDesignCore) | the geometry, validated and provenance-carrying |

Inventory is mutable user state and deliberately does not live in the registry (platform decision PD-2).

## Not this

- Not a parts database. Facts about parts belong upstream, with citations.
- Not a store: no pricing, no stock. Those are live and belong to distributor APIs, keyed by the ids here.
- Not a scheduler or a BOM tool.
- Not a slicer. `machines.py` does pre-slicing triage — fit, material, feature floor — and hands anything requiring toolpaths to a real slicer.

## License

Apache-2.0 — see [LICENSE](LICENSE).
