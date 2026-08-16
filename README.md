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

Also: `advisor.py inventory`, `advisor.py gaps <project-id>`, and `--json` on any command.

## How it works

- **Inventory** (`example/inventory.json`) is a list of `part_id` + `qty`. Every id must exist in [OpenPartsCore](https://github.com/thewriterben/OpenPartsCore) — inventory that can't be resolved is refused rather than half-understood.
- **Projects** (`data/projects/*.json`) declare requirements as either a specific `part_id` or a `capability` any part may provide, each with a quantity.
- **Matching** allocates owned stock to requirements **exclusively**: one unit satisfies at most one requirement. A single ESP32 cannot be both nodes of a two-node mesh.
- **Suggestions** for a missing capability are found by **searching the registry**, so they improve as the registry grows. No hand-maintained lists.

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

## License

Apache-2.0 — see [LICENSE](LICENSE).
