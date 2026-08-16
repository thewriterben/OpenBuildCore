# obc_mcp — MCP surface

Exposes the build advisor to any MCP client, so an agent can answer "what can I build with what I own" without shelling out to the CLI.

## Install and register

```
pip install -r obc_mcp/requirements.txt
claude mcp add openbuildcore --scope user -- python -m obc_mcp.server
```

Verified connected against a real client, not just imported.

Environment: `OBC_INVENTORY` (default `example/inventory.json`), `OPC_DIR` (default `../OpenPartsCore`).

## Tools

| Tool | Does |
|---|---|
| `inventory` | What the user owns — ids, quantities, capabilities |
| `list_projects` | Known projects and their requirements |
| `what_can_i_build` | Every project evaluated against the inventory |
| `gaps` | One project's shortfalls, with registry-derived suggestions |
| `shopping_list` | Gaps aggregated, with an explicit sequential/simultaneous basis |

## Why everything executes

OpenDesignCore ADR-0009 draws the line at the store boundary: effects confined to a peer's own content-addressed stores execute, anything reaching beyond stops at a proposal. Nothing here writes to a store, moves hardware, or reaches a fabricator — so all five tools execute, and there is nothing to propose.

**There is deliberately no tool that edits inventory.** Inventory is the user's own record of physical objects. An agent quietly deciding you own three more resistors than you do would poison every answer downstream, and the error would only surface at the bench.

## Note on the SDK

Written against **MCP Python SDK 2.x**, where `MCPServer` replaced `FastMCP`. `mcp.server.fastmcp` no longer exists — AdvancedStudio's `studio-mcp` still imports it and does not start against 2.0.0. The package here is named `obc_mcp` rather than `mcp` so it cannot shadow the SDK.
